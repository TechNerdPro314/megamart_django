from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from apps.cart.services import CartService, DELIVERY_OPTIONS
from .forms import CheckoutForm
from .services import CheckoutService, OrderCreationError, StockReservationError
from .tasks import send_order_notifications


@login_required 
def checkout_view(request):
    cart = CartService(request)

    if cart.get_total_quantity() == 0:
        messages.error(request, "Корзина пуста. Добавьте товары перед оформлением заказа.")
        return redirect("cart:cart_detail")

    current_delivery = cart.get_delivery_method()

    if request.method == "POST":
        if not current_delivery:
            messages.error(request, "Пожалуйста, выберите способ доставки.")
            return redirect("orders:checkout")

        form = CheckoutForm(request.POST)
        if form.is_valid():
            try:
                checkout_service = CheckoutService(request)
                order = checkout_service.create_order(form.cleaned_data)

                coupon_data = cart.get_coupon()
                if coupon_data:
                    order.coupon_code = coupon_data.get('code')
                    order.discount_amount = cart.get_discount_amount()
                    order.total_amount = cart.get_final_price()
                    order.save(update_fields=['coupon_code', 'discount_amount', 'total_amount'])

                # Отправляем уведомления (email и т.п.)
                send_order_notifications.delay(order.id)

                # НЕ очищаем корзину здесь – она очистится позже, после оплаты
                # cart.clear()

                # Перенаправляем на страницу подтверждения заказа
                return redirect("orders:order_created", order_id=order.id)

            except OrderCreationError as e:
                messages.error(request, f"Ошибка: {e}")
            except StockReservationError as e:
                messages.error(request, f"Товар недоступен: {e}")
            except Exception as e:
                messages.error(request, f"Произошла ошибка: {e}")
        # Если форма невалидна – покажем её снова с ошибками
    else:
        initial = {}
        if request.user.is_authenticated:
            initial.update({
                "customer_name": f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                "customer_email": request.user.email or "",
                "customer_phone": getattr(request.user, 'phone', '') or "",
            })
        initial['delivery_method'] = current_delivery or ""
        form = CheckoutForm(initial=initial)

    return render(request, "orders/checkout.html", {
        "form": form,
        "cart": cart,
        "delivery_options": DELIVERY_OPTIONS,
        "current_delivery": current_delivery,
    })


def order_created_view(request, order_id):
    """Страница подтверждения создания заказа перед оплатой."""
    from .models import Order

    order = Order.objects.filter(id=order_id).first()
    if not order:
        messages.error(request, "Заказ не найден.")
        return redirect("catalog:product_list")

    # Если заказ уже оплачен – перенаправляем на детали
    if order.status in ["paid", "processing"]:
        return redirect("orders:order_detail", order_id=order.id)

    # Показываем страницу с кнопкой «Оплатить»
    return render(request, "orders/order_created.html", {"order": order})


@login_required
def order_detail_view(request, order_id):
    """Детали заказа (для авторизованных пользователей)"""
    from .models import Order

    order = Order.objects.filter(
        id=order_id,
        user=request.user
    ).first()

    if not order:
        messages.error(request, "Заказ не найден")
        return redirect("catalog:product_list")

    has_payment = hasattr(order, 'payment') and order.payment
    needs_payment = order.status in ["new", "confirmed"] and (
        not has_payment or order.payment.status in ["pending", "canceled"]
    )

    return render(request, "orders/order_detail.html", {
        "order": order,
        "needs_payment": needs_payment,
    })


@login_required
def my_orders_view(request):
    """Список заказов пользователя"""
    from .models import Order

    orders = Order.objects.filter(
        user=request.user
    ).select_related().order_by("-created_at")

    return render(request, "orders/my_orders.html", {"orders": orders})


def pay_order_view(request, order_id):
    """Оплата заказа – перенаправление в модуль payments"""
    return redirect("payments:pay_order", order_id=order_id)


def order_success_view(request, order_id):
    """Страница успешного оформления заказа (после оплаты)"""
    from .models import Order

    if request.user.is_authenticated:
        order = Order.objects.filter(id=order_id, user=request.user).first()
    else:
        order = Order.objects.filter(id=order_id).first()

    if not order:
        messages.error(request, "Заказ не найден")
        return redirect("catalog:product_list")

    return render(request, "orders/success.html", {"order": order})