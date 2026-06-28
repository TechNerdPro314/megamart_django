# apps/cart/views.py

from django.shortcuts import redirect, render, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from apps.catalog.models import Product
from .services import CartService


@login_required  
def cart_detail_view(request):
    """Отображение корзины"""
    cart = CartService(request)
    return render(request, "cart/cart.html", {"cart": cart})


@require_POST
def add_to_cart_view(request, product_id):
    """Добавление товара в корзину"""
    cart = CartService(request)
    product = get_object_or_404(Product, id=product_id, is_active=True)

    qty = max(1, int(request.POST.get("quantity", 1)))
    success = cart.add(product.id, qty)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        summary = cart.get_summary()
        return JsonResponse({
            'success': success,
            'total_quantity': summary['total_quantity'],
            'subtotal': round(float(summary['subtotal']), 2),
            'discount': round(float(summary.get('discount', 0)), 2),
            'delivery_cost': round(float(summary.get('delivery_cost', 0)), 2),
            'total': round(float(summary['total']), 2),
            'items_count': summary['items_count'],
            'message': f"{product.name} добавлен в корзину." if success else "Не удалось добавить товар.",
        })

    if success:
        messages.success(request, f"{product.name} добавлен в корзину.")
    else:
        messages.error(request, "Не удалось добавить товар в корзину.")
    return redirect("cart:cart_detail")


@require_POST
def remove_from_cart_view(request, product_id):
    """Удаление товара из корзины"""
    cart = CartService(request)
    cart.remove(product_id)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        summary = cart.get_summary()
        return JsonResponse({
            'success': True,
            'total_quantity': summary['total_quantity'],
            'subtotal': round(float(summary['subtotal']), 2),
            'discount': round(float(summary.get('discount', 0)), 2),
            'delivery_cost': round(float(summary.get('delivery_cost', 0)), 2),
            'total': round(float(summary['total']), 2),
            'items_count': summary['items_count'],
        })

    messages.info(request, "Товар удален из корзины.")
    return redirect("cart:cart_detail")


@require_POST
def update_cart_view(request, product_id):
    """Обновление количества товара в корзине"""
    cart = CartService(request)
    qty = max(0, int(request.POST.get("quantity", 1)))
    success = cart.update(product_id, qty)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        summary = cart.get_summary()
        return JsonResponse({
            'success': success,
            'total_quantity': summary['total_quantity'],
            'subtotal': round(float(summary['subtotal']), 2),
            'discount': round(float(summary.get('discount', 0)), 2),
            'delivery_cost': round(float(summary.get('delivery_cost', 0)), 2),
            'total': round(float(summary['total']), 2),
            'items_count': summary['items_count'],
        })

    messages.success(request, "Корзина обновлена.")
    return redirect("cart:cart_detail")


@require_POST
def apply_coupon_view(request):
    """Применение купона"""
    cart = CartService(request)
    code = request.POST.get("coupon", "").strip()

    if not code:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'Введите код купона.'})
        messages.error(request, "Введите код купона.")
        return redirect("cart:cart_detail")

    coupon = cart.apply_coupon(code)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if coupon:
            summary = cart.get_summary()
            if coupon.discount_type == 'percent':
                discount_desc = f"{coupon.discount_value}%"
            else:
                discount_desc = f"{coupon.discount_value} ₽"

            return JsonResponse({
                'success': True,
                'message': f"Купон {coupon.code} применен (скидка {discount_desc}).",
                'coupon_code': coupon.code,
                'discount': round(float(summary.get('discount', 0)), 2),
                'subtotal': round(float(summary['subtotal']), 2),
                'delivery_cost': round(float(summary.get('delivery_cost', 0)), 2),
                'total': round(float(summary['total']), 2),
            })
        else:
            return JsonResponse({'success': False, 'message': 'Неверный или просроченный купон, либо не достигнута минимальная сумма заказа.'})

    if coupon:
        if coupon.discount_type == 'percent':
            discount_desc = f"{coupon.discount_value}%"
        else:
            discount_desc = f"{coupon.discount_value} ₽"
        messages.success(request, f"Купон {coupon.code} применен (скидка {discount_desc}).")
    else:
        messages.error(request, "Неверный или просроченный купон, либо не достигнута минимальная сумма заказа.")
    return redirect("cart:cart_detail")


@require_POST
def remove_coupon_view(request):
    """Удаление купона"""
    cart = CartService(request)
    cart.remove_coupon()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        summary = cart.get_summary()
        return JsonResponse({
            'success': True,
            'message': 'Купон удален.',
            'discount': 0,
            'subtotal': round(float(summary['subtotal']), 2),
            'delivery_cost': round(float(summary.get('delivery_cost', 0)), 2),
            'total': round(float(summary['total']), 2),
        })

    messages.info(request, "Купон удален.")
    return redirect("cart:cart_detail")


@require_POST
def set_delivery_view(request):
    cart = CartService(request)
    method = request.POST.get("delivery_method", "")

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        success = cart.set_delivery_method(method)
        summary = cart.get_summary()
        return JsonResponse({
            'success': success,
            'subtotal': round(float(summary['subtotal']), 2),
            'delivery_cost': round(float(summary['delivery_cost']), 2),
            'discount': round(float(summary.get('discount', 0)), 2),
            'total': round(float(summary['total']), 2),
        })

    if cart.set_delivery_method(method):
        messages.success(request, "Способ доставки обновлен.")
    else:
        messages.error(request, "Неверный способ доставки.")
    return redirect("cart:cart_detail")


@require_POST
def clear_cart_view(request):
    """Очистка корзины"""
    cart = CartService(request)
    cart.clear()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'total_quantity': 0,
            'subtotal': 0.00,
            'discount': 0.00,
            'delivery_cost': 0.00,
            'total': 0.00,
            'items_count': 0,
        })

    messages.info(request, "Корзина очищена.")
    return redirect("cart:cart_detail")