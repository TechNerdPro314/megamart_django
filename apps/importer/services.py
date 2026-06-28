import uuid
import openpyxl
from decimal import Decimal, InvalidOperation
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.utils.text import slugify
from apps.catalog.models import Product, Category, Brand, Attribute, ProductAttributeValue


class ExcelImportError(Exception):
    pass


class ExcelImporter:
    """
    Выполняет импорт товаров из Excel-файла в соответствии с ImportProfile.
    """

    def __init__(self, job):
        self.job = job
        self.profile = job.profile
        self.field_mapping = self.profile.field_mapping or {}
        self.default_values = self.profile.default_values or {}
        self.stats = {'total': 0, 'success': 0, 'error': 0}
        self.errors = []
        self._header = None

    def run(self):
        self.job.status = 'processing'
        self.job.save(update_fields=['status'])
        try:
            wb = openpyxl.load_workbook(self.job.file.path, data_only=True)
            if self.profile.sheet_name:
                ws = wb[self.profile.sheet_name]
            else:
                ws = wb.active

            rows = list(ws.iter_rows(values_only=True))
            start_row = 0
            if self.profile.skip_header and rows:
                self._header = rows[0]          # сохраняем заголовок один раз
                start_row = 1
            else:
                self._header = None

            total = max(0, len(rows) - start_row)
            self.job.total_rows = total
            self.job.save(update_fields=['total_rows'])

            for row_idx, row in enumerate(rows[start_row:], start=start_row + 1):
                try:
                    self._process_row(row, row_idx)
                    self.stats['success'] += 1
                except Exception as e:
                    error_msg = f"Строка {row_idx}: {e}"
                    self.errors.append(error_msg)
                    self.stats['error'] += 1

            self.job.success_count = self.stats['success']
            self.job.error_count = self.stats['error']
            if self.errors:
                self.job.append_log('\n'.join(self.errors))
            else:
                self.job.append_log("Импорт завершён без ошибок.")
            self.job.status = 'completed'
        except Exception as e:
            self.job.append_log(f"Критическая ошибка: {e}")
            self.job.status = 'failed'
        finally:
            self.job.completed_at = timezone.now()
            self.job.save(update_fields=['status', 'success_count', 'error_count', 'log', 'completed_at'])

    def _process_row(self, row, row_number):
        data = {}
        # Собираем данные из столбцов по маппингу
        for field_name, column_name in self.field_mapping.items():
            col_idx = self._find_column_index(column_name)
            if col_idx is not None:
                value = row[col_idx] if col_idx < len(row) else None
            else:
                value = None
            # Применяем значение по умолчанию, если пусто
            if (value is None or str(value).strip() == '') and field_name in self.default_values:
                value = self.default_values[field_name]
            data[field_name] = value

        # Извлекаем или создаём связанные объекты
        category = self._get_or_cache_category(data.get('category__name'))
        brand = self._get_or_cache_brand(data.get('brand__name'))

        # Основные поля товара
        sku = str(data.get('sku', '')).strip()
        name = str(data.get('name', '')).strip()

        if not name:
            raise ValueError("Отсутствует название товара")

        # Если SKU пустой – генерируем уникальный
        if not sku:
            base_sku = slugify(name)[:16].upper()
            random_suffix = uuid.uuid4().hex[:6].upper()
            sku = f"{base_sku}-{random_suffix}"
            # Дополнительно убедимся, что такой SKU не существует
            while Product.objects.filter(sku=sku).exists():
                random_suffix = uuid.uuid4().hex[:6].upper()
                sku = f"{base_sku}-{random_suffix}"

        price = self._parse_decimal(data.get('price'))
        stock = self._parse_int(data.get('stock', 0))

        # Ищем существующий товар по SKU
        existing_product = Product.objects.filter(sku=sku).first()
        if existing_product and not self.profile.update_existing:
            raise ValueError(f"Товар с SKU {sku} уже существует (обновление отключено)")

        defaults = {
            'name': name,
            'slug': data.get('slug') if data.get('slug') else None,
            'price': price if price is not None else Decimal('0'),
            'stock': stock,
            'short_description': str(data.get('short_description', '')) or None,
            'description': str(data.get('description', '')) or None,
            'is_active': self._parse_bool(data.get('is_active', True)),
            'category': category or self.profile.default_category,
            'brand': brand or self.profile.default_brand,
            'seo_title': str(data.get('seo_title', '')) or None,
            'seo_description': str(data.get('seo_description', '')) or None,
            'seo_keywords': str(data.get('seo_keywords', '')) or None,
        }

        try:
            if existing_product:
                # Обновляем существующий товар
                for key, value in defaults.items():
                    if value is not None:
                        setattr(existing_product, key, value)
                existing_product.save()
            else:
                # Создаём новый товар
                if not defaults.get('slug'):
                    defaults['slug'] = self._generate_slug(name)
                product = Product(**defaults)
                product.save()
        except IntegrityError as e:
            # Ловим дубликаты (например, slug уже существует)
            raise ValueError(f"Ошибка сохранения товара: {e}")

        # Импорт атрибутов (опционально)
        attr_fields = {k: v for k, v in data.items() if k.startswith('attribute__')}
        for field_name, value in attr_fields.items():
            attr_name = field_name.split('__')[1]
            self._set_attribute(product if not existing_product else existing_product, attr_name, str(value) if value else None)

    def _find_column_index(self, column_name):
        """Ищет индекс столбца в сохранённом заголовке (self._header)."""
        if self._header is None:
            return None
        try:
            return self._header.index(column_name)
        except ValueError:
            return None

    def _get_or_cache_category(self, name):
        if not name:
            return None
        name = str(name).strip()
        if not name:
            return None
        return Category.objects.filter(name__iexact=name, is_active=True).first()

    def _get_or_cache_brand(self, name):
        if not name:
            return None
        name = str(name).strip()
        if not name:
            return None
        return Brand.objects.filter(name__iexact=name, is_active=True).first()

    def _parse_decimal(self, value):
        if value is None or str(value).strip() == '':
            return None
        try:
            return Decimal(str(value).replace(',', '.'))
        except InvalidOperation:
            raise ValueError(f"Некорректная цена: {value}")

    def _parse_int(self, value):
        try:
            return int(value) if value is not None else 0
        except (ValueError, TypeError):
            return 0

    def _parse_bool(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes', 'да')
        return bool(value)

    def _generate_slug(self, name):
        slug = slugify(name)
        if Product.objects.filter(slug=slug).exists():
            slug = f"{slug}-{Product.objects.count()}"
        return slug

    def _set_attribute(self, product, attr_name, value):
        if not value:
            return
        attr, created = Attribute.objects.get_or_create(
            name__iexact=attr_name,
            defaults={'name': attr_name}
        )
        ProductAttributeValue.objects.update_or_create(
            product=product,
            attribute=attr,
            defaults={'value': value}
        )