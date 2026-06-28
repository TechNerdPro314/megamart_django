"""
Команда Django для заполнения сайта тестовыми данными с картинками.
Выполняется: python manage.py fill_test_data
"""
import random
import os
import io
from decimal import Decimal
from PIL import Image, ImageDraw, ImageFont

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.contrib.auth import get_user_model
from django.db import transaction
from django.conf import settings
from django.core.files.base import ContentFile

from apps.catalog.models import Category, Brand, Attribute, Product, ProductImage, ProductAttributeValue
from apps.orders.models import Order, OrderItem
from apps.promotions.models import Coupon

User = get_user_model()

# Маппинг типов товаров на slug категорий
TYPE_CATEGORY_MAP = {
    "compact": "unitazy",
    "comfort": "unitazy",
    "toilet": "unitazy",
    "sink": "rakoviny",
    "pedestal": "rakoviny",
    "bathtub": "vanny",
    "cast_iron": "vanny",
    "shower": "dushevye-sistemy",
    "booth": "dushevye-sistemy",
    "faucet": "smesiteli",
    "bathtub_faucet": "smesiteli",
    "bidet": "bidet",
    "hydro": "gidromassazh",
    "accessory": "aksessuary",
}


def generate_test_image(product_name: str) -> ContentFile:
    """Создаёт тестовое изображение 800x600 с названием товара."""
    width, height = 800, 600
    bg_color = tuple(random.randint(180, 255) for _ in range(3))
    img = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except IOError:
        font = ImageFont.load_default()

    text = product_name[:50]
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) / 2
    y = (height - text_height) / 2
    draw.text((x, y), text, fill="black", font=font)

    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    buffer.seek(0)
    return ContentFile(buffer.read(), name=f"{slugify(product_name)[:40]}.jpg")


class Command(BaseCommand):
    help = "Заполняет сайт тестовыми данными (категории, бренды, товары с картинками, пользователи, заказы)"

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Очистить данные перед заполнением')
        parser.add_argument('--categories', type=int, default=8, help='Количество категорий (макс. 8)')
        parser.add_argument('--brands', type=int, default=10, help='Количество брендов')
        parser.add_argument('--products', type=int, default=50, help='Количество товаров')
        parser.add_argument('--users', type=int, default=20, help='Количество пользователей')
        parser.add_argument('--orders', type=int, default=30, help='Количество заказов')

    def handle(self, *args, **options):
        clear_data = options['clear']
        num_categories = min(options['categories'], 8)
        num_brands = options['brands']
        num_products = options['products']
        num_users = options['users']
        num_orders = options['orders']

        if clear_data:
            self.stdout.write(self.style.WARNING("Очистка существующих данных..."))
            with transaction.atomic():
                ProductImage.objects.all().delete()
                ProductAttributeValue.objects.all().delete()
                Product.objects.all().delete()
                Attribute.objects.all().delete()
                Brand.objects.all().delete()
                Category.objects.all().delete()
                OrderItem.objects.all().delete()
                Order.objects.all().delete()
                Coupon.objects.all().delete()
                User.objects.filter(is_superuser=False, username__startswith='user').delete()
            self.stdout.write(self.style.SUCCESS("Данные очищены!"))

        # Создаем категории
        self.stdout.write(f"\nСоздание категорий...")
        categories_data = [
            {"name": "Унитазы", "slug": "unitazy", "description": "Современные унитазы от ведущих производителей"},
            {"name": "Раковины", "slug": "rakoviny", "description": "Элегантные раковины для ванной комнаты"},
            {"name": "Ванны", "slug": "vanny", "description": "Комфортные ванны для релаксации"},
            {"name": "Душевые системы", "slug": "dushevye-sistemy", "description": "Полные душевые комплекты и кабины"},
            {"name": "Смесители", "slug": "smesiteli", "description": "Надежные смесители для кухни и ванной"},
            {"name": "Биде", "slug": "bidet", "description": "Современные биде для комфортной гигиены"},
            {"name": "Гидромассаж", "slug": "gidromassazh", "description": "Системы гидромассажа и джакузи"},
            {"name": "Аксессуары", "slug": "aksessuary", "description": "Сантехнические аксессуары и принадлежности"},
        ][:num_categories]

        categories = {}
        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                slug=cat_data["slug"],
                defaults={
                    "name": cat_data["name"],
                    "description": cat_data["description"],
                    "is_active": True,
                }
            )
            categories[cat_data["slug"]] = category
            if created:
                self.stdout.write(f"  ✓ Категория: {category.name}")

        # Создаем бренды
        self.stdout.write(f"\nСоздание {num_brands} брендов...")
        brands_data = [
            "Grohe", "Hansgrohe", "Roca", "Jacob Delafon", "Cersanit",
            "Ifö", "Gustavsberg", "Vitra", "Kerama Marazzi", "Aquabella",
            "Tece", "Geberit", "Laufen", "Ideon", "Santech",
        ][:num_brands]

        brands = []
        for brand_name in brands_data:
            brand, created = Brand.objects.get_or_create(
                name=brand_name,
                defaults={"slug": slugify(brand_name), "is_active": True}
            )
            brands.append(brand)
            if created:
                self.stdout.write(f"  ✓ Бренд: {brand.name}")

        # Создаем атрибуты (с русским названием и английским slug)
        self.stdout.write("\nСоздание атрибутов...")
        attributes_data = [
            ("Материал", "material"),
            ("Цвет", "color"),
            ("Размер", "size"),
            ("Гарантия", "warranty"),
            ("Страна производства", "country"),
            ("Тип монтажа", "installation"),
            ("Объем бачка", "tank-volume"),
            ("Форма чаши", "bowl-shape"),
            ("Мягкое сиденье", "soft-seat"),
        ]
        attributes = []
        for attr_name, attr_slug in attributes_data:
            attr, created = Attribute.objects.get_or_create(
                slug=attr_slug,
                defaults={"name": attr_name, "is_filterable": True}
            )
            attributes.append(attr)
            if created:
                self.stdout.write(f"  ✓ Атрибут: {attr.name}")

        # Создаем товары с правильными категориями
        self.stdout.write(f"\nСоздание {num_products} товаров с изображениями...")
        product_templates = [
            ("Унитаз подвесной {brand} Slim", 15000, "compact"),
            ("Унитаз напольный {brand} Comfort", 12000, "comfort"),
            ("Раковина навесная {brand} Elegance", 8000, "sink"),
            ("Раковина с пьедесталом {brand} Classic", 10000, "pedestal"),
            ("Ванна акриловая {brand} Relax 170x70", 25000, "bathtub"),
            ("Ванна чугунная {brand} Standard 150x70", 18000, "cast_iron"),
            ("Душевая система {brand} Rain", 35000, "shower"),
            ("Смеситель для раковины {brand} Mono", 5000, "faucet"),
            ("Смеситель для ванны {brand} Dual", 7000, "bathtub_faucet"),
            ("Биде {brand} Modern", 9000, "bidet"),
            ("Гидромассажная система {brand} Pro", 55000, "hydro"),
            ("Душевая кабина {brand} Premium", 45000, "booth"),
        ]

        products_created = 0
        for i in range(num_products):
            template = random.choice(product_templates)
            brand = random.choice(brands)
            product_type = template[2]
            category_slug = TYPE_CATEGORY_MAP.get(product_type)
            category = categories.get(category_slug) if category_slug else random.choice(list(categories.values()))

            name = template[0].format(brand=brand.name)
            sku = f"MM-{random.randint(10000, 99999)}"
            price = Decimal(str(template[1] + random.randint(-2000, 5000)))

            base_slug = slugify(name)
            slug = f"{base_slug}-{random.randint(1000, 9999)}"

            product, created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "slug": slug,
                    "category": category,
                    "brand": brand,
                    "price": price,
                    "stock": random.randint(5, 100),
                    "short_description": f"Качественный {name.lower()} от {brand.name}",
                    "description": self._get_product_description(name, brand, category),
                    "is_active": True,
                    "is_featured": random.random() > 0.8,
                }
            )

            if created:
                products_created += 1
                self.stdout.write(f"  ✓ Товар: {product.name} (категория: {category.name})")

                for attr in random.sample(attributes, random.randint(2, 4)):
                    attr_value = self._get_attribute_value(attr.name, product)
                    ProductAttributeValue.objects.create(
                        product=product,
                        attribute=attr,
                        value=attr_value
                    )

                try:
                    image_content = generate_test_image(product.name)
                    ProductImage.objects.create(
                        product=product,
                        image=image_content,
                        is_main=True,
                        alt_text=product.name
                    )
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"    ⚠ Не удалось создать изображение: {e}"))

        self.stdout.write(self.style.SUCCESS(f"\nСоздано {products_created} товаров"))

        # Пользователи, заказы, купоны (аналогично предыдущей версии)
        self.stdout.write(f"\nСоздание {num_users} пользователей...")
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@megamart.ru', 'is_superuser': True, 'is_staff': True}
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write("  ✓ Суперпользователь: admin / admin123")

        for i in range(num_users):
            username = f"user{i+1}"
            email = f"user{i+1}@example.com"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "first_name": f"Имя{i+1}",
                    "last_name": f"Фамилия{i+1}",
                    "phone": f"+7 (999) {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}",
                }
            )
            if created:
                user.set_password('password123')
                user.save()

        self.stdout.write(f"\nСоздание {num_orders} заказов...")
        users = list(User.objects.filter(is_superuser=False))
        products = list(Product.objects.all())
        if users and products:
            for i in range(num_orders):
                user = random.choice(users)
                order_items = random.sample(products, min(random.randint(1, 4), len(products)))
                subtotal = sum(p.price for p in order_items)
                delivery_cost = Decimal(random.choice([500, 700, 1000, 0]))
                total = subtotal + delivery_cost
                delivery_method = random.choice(["courier", "pickup", "post"])
                order = Order.objects.create(
                    user=user,
                    customer_name=f"{user.first_name} {user.last_name}",
                    customer_email=user.email,
                    customer_phone=user.phone,
                    delivery_method=delivery_method,
                    delivery_address="г. Москва, ул. Тестовая, д. 1" if delivery_method != "pickup" else "",
                    comment="Тестовый заказ",
                    subtotal_amount=subtotal,
                    delivery_cost=delivery_cost,
                    total_amount=total,
                    payment_method=random.choice(["card", "cash", "online"]),
                    status=random.choice(["new", "confirmed", "paid", "processing", "shipped", "delivered", "cancelled"]),
                )
                for product in order_items:
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_name=product.name,
                        product_sku=product.sku,
                        price=product.price,
                        quantity=random.randint(1, 3),
                        total_price=product.price * random.randint(1, 3),
                    )

        self.stdout.write("\nСоздание промокодов...")
        from datetime import timedelta
        from django.utils import timezone
        now = timezone.now()
        coupons_data = [
            {"code": "WELCOME10", "name": "Приветственная скидка", "discount_type": "percent", "discount_value": 10, "min_order_amount": 5000, "active": True, "valid_from": now - timedelta(days=1), "valid_to": now + timedelta(days=365)},
            {"code": "SUMMER20", "name": "Летняя акция", "discount_type": "percent", "discount_value": 20, "min_order_amount": 10000, "active": True, "valid_from": now - timedelta(days=1), "valid_to": now + timedelta(days=180)},
            {"code": "FIRST500", "name": "Скидка новым клиентам", "discount_type": "fixed", "discount_value": 500, "min_order_amount": 3000, "active": True, "valid_from": now - timedelta(days=1), "valid_to": now + timedelta(days=365)},
            {"code": "FREESHIP", "name": "Бесплатная доставка", "discount_type": "fixed", "discount_value": 1000, "min_order_amount": 15000, "active": True, "valid_from": now - timedelta(days=1), "valid_to": now + timedelta(days=90)},
        ]
        for coupon_data in coupons_data:
            Coupon.objects.get_or_create(code=coupon_data["code"], defaults=coupon_data)

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 50))
        self.stdout.write(self.style.SUCCESS("✓ Все тестовые данные успешно созданы!"))
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write("\nДоступ к данным:")
        self.stdout.write("  - Суперпользователь: admin / admin123")
        self.stdout.write("  - Пользователи: user1-user20 / password123")
        self.stdout.write("  - Админ-панель: http://127.0.0.1:8000/admin/")

    def _get_product_description(self, name, brand, category):
        descriptions = [
            f"Высококачественный {name.lower()} от бренда {brand.name}. "
            f"Отличается надежностью, долговечностью и современным дизайном. "
            f"Идеально подходит для вашей {category.name.lower()}. "
            f"Официальная гарантия производителя. Легкий монтаж и обслуживание.",
            f"Профессиональный {name.lower()} {brand.name} - выбор экспертов. "
            f"Создан с использованием передовых технологий и лучших материалов. "
            f"Обеспечивает максимальный комфорт и экономичность. "
            f"Сертифицированное качество, полное соответствие стандартам.",
            f"Современный {name.lower()} от лидера рынка {brand.name}. "
            f"Сочетает в себе элегантный дизайн и функциональность. "
            f"Прост в уходе и эксплуатации. "
            f"Отличный выбор для дома и офиса.",
        ]
        return random.choice(descriptions)

    def _get_attribute_value(self, attr_name, product):
        values = {
            "Материал": random.choice(["Керамика", "Фарфор", "Акрил", "Чугун", "Нержавеющая сталь", "Пластик"]),
            "Цвет": random.choice(["Белый", "Бежевый", "Серый", "Черный", "Коричневый", "Синий"]),
            "Размер": random.choice(["Стандарт", "Компакт", "Large", "XL", "Мини"]),
            "Гарантия": random.choice(["1 год", "2 года", "5 лет", "10 лет"]),
            "Страна производства": random.choice(["Германия", "Италия", "Чехия", "Россия", "Турция"]),
            "Тип монтажа": random.choice(["Напольный", "Подвесной", "Накладной", "Встраиваемый"]),
            "Объем бачка": random.choice(["3/6 л", "4/8 л", "5/10 л", "6/12 л"]),
            "Форма чаши": random.choice(["Круглая", "Овальная", "Прямоугольная", "Капелька"]),
            "Мягкое сиденье": random.choice(["Да", "Нет", "Микролифт"]),
        }
        return values.get(attr_name, "Стандарт")