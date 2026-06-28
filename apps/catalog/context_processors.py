# apps/catalog/context_processors.py
from .models import Category

def footer_categories(request):
    """
    Добавляет список активных категорий (с непустым slug) в контекст всех шаблонов,
    чтобы футер мог использовать их реальные slug'и для ссылок.
    """
    categories = Category.objects.filter(is_active=True).exclude(slug='')[:10]
    return {'footer_categories': categories}