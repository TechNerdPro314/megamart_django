from decimal import Decimal
from typing import Dict, Any, Optional, Tuple
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.cart.services import CartService
from apps.catalog.models import Product
from apps.promotions.models import Coupon
from apps.notifications.services import send_order_notification
from .models import Order, OrderItem, OrderStatus


class OrderCreationError(Exception):
    """Ошибка создания заказа"""
    pass


class StockReservationError(Exception):
    """Ошибка резервирования товаров"""
    pass


class CheckoutService:
    """
    Сервис оформления заказа
    
    Функционал:
    - Валидация корзины и данных клиента
    - Резервирование товаров на складе
    - Создание заказа из корзины
    - Отправка уведомлений
    """
    
    def __init__(self, request):
        self.request = request
        self.cart = CartService(request)
    
    @transaction.atomic
    def create_order(self, cleaned_data: Dict[str, Any]) -> Order:
        """
        Создаёт заказ из корзины
        
        Args:
            cleaned_data: Очищенные данные из формы CheckoutForm
            
        Returns:
            Order: Созданный заказ
            
        Raises:
            OrderCreationError: Если не удалось создать заказ
        """
        # Извлекаем способ доставки из формы и удаляем, чтобы не передавать в Order
        delivery_method = cleaned_data.pop('delivery_method', None)
        
        # Дополнительная проверка: если в форме нет, берём из корзины
        if not delivery_method:
            delivery_method = self.cart.get_delivery_method()
        
        if not delivery_method:
            raise OrderCreationError("Выберите способ доставки")
        
        # Убедимся, что корзина знает выбранный способ (на случай, если ещё не сохранён)
        if self.cart.get_delivery_method() != delivery_method:
            self.cart.set_delivery_method(delivery_method)
        
        # Проверка: корзина не пуста
        if self.cart.get_total_quantity() == 0:
            raise OrderCreationError("Корзина пуста")
        
        # Валидация товаров и резервирование стока
        self._validate_and_reserve_stock()
        
        # Расчет сумм
        subtotal = self.cart.get_subtotal_price()
        discount = self.cart.get_discount_amount()
        delivery_cost = self.cart.get_delivery_cost()
        total = self.cart.get_final_price()
        
        # Получение данных о купоне
        coupon_data = self.cart.get_coupon()
        coupon_code = coupon_data['code'] if coupon_data else ""
        
        # Создание заказа
        order = Order.objects.create(
            user=self.request.user if self.request.user.is_authenticated else None,
            customer_name=cleaned_data.get("customer_name", cleaned_data.get("first_name", "")),
            customer_phone=cleaned_data.get("customer_phone", cleaned_data.get("phone", "")),
            customer_email=cleaned_data.get("customer_email", cleaned_data.get("email", "")),
            delivery_address=cleaned_data.get("delivery_address", cleaned_data.get("address", "")),
            delivery_method=delivery_method,            # важно: поле есть в модели
            comment=cleaned_data.get("comment", ""),
            manager_comment=cleaned_data.get("manager_comment", ""),
            payment_method=cleaned_data.get("payment_method", "card"),
            subtotal_amount=subtotal,
            discount_amount=discount,
            delivery_cost=delivery_cost,
            coupon_code=coupon_code,
            total_amount=total,
            status=OrderStatus.NEW,
        )
        
        # Создание элементов заказа
        for item in self.cart:
            OrderItem.objects.create(
                order=order,
                product=item.product,
                product_name=item.product.name,
                product_sku=item.product.sku or "",
                price=item.product.price,
                quantity=item.quantity,
                total_price=item.total_price,
            )
        
        # Отправка уведомлений
        self._send_notifications(order)
        
        # Очистка корзины
        self.cart.clear()
        
        return order
    
    def _validate_and_reserve_stock(self) -> None:
        """
        Проверяет наличие товаров и резервирует сток
        
        Raises:
            StockReservationError: Если товара нет в наличии
        """
        for item in self.cart:
            product = item.product
            
            # Проверка: товар активен
            if not product.is_active:
                raise StockReservationError(f"Товар '{product.name}' больше не доступен")
            
            # Проверка: достаточное количество на складе
            if product.stock < item.quantity:
                raise StockReservationError(
                    f"Недостаточно товара '{product.name}'. "
                    f"Доступно: {product.stock}, требуется: {item.quantity}"
                )
            
            # Резервирование стока
            self._reserve_product_stock(product, item.quantity)
    
    def _reserve_product_stock(self, product: Product, quantity: int) -> None:
        """
        Резервирует количество товара на складе
        
        Args:
            product: Товар для резервирования
            quantity: Количество для резервирования
        """
        product.stock = max(0, product.stock - quantity)
        product.save(update_fields=['stock', 'updated_at'])
    
    def _send_notifications(self, order: Order) -> None:
        """
        Отправляет уведомления о создании заказа
        
        Args:
            order: Созданный заказ
        """
        try:
            # Уведомление клиента
            send_order_notification(
                recipient_email=order.customer_email,
                recipient_name=order.customer_name,
                order=order,
                notification_type="customer"
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления клиенту: {e}")
        
        try:
            # Уведомление менеджера (если есть админы)
            from django.contrib.auth import get_user_model
            User = get_user_model()
            admins = User.objects.filter(is_staff=True, is_active=True)
            for admin in admins:
                if admin.email:
                    send_order_notification(
                        recipient_email=admin.email,
                        recipient_name=admin.get_full_name() or admin.username,
                        order=order,
                        notification_type="manager"
                    )
        except Exception as e:
            print(f"Ошибка отправки уведомления менеджеру: {e}")
    
    def validate_cart(self) -> Tuple[bool, str]:
        """
        Проверяет корректность корзины для оформления заказа
        
        Returns:
            Tuple[bool, str]: (успешно, сообщение)
        """
        if self.cart.get_total_quantity() == 0:
            return False, "Корзина пуста"
        
        if not self.cart.get_delivery_method():
            return False, "Выберите способ доставки"
        
        # Проверка наличия товаров
        for item in self.cart:
            if not item.product.is_active:
                return False, f"Товар '{item.product.name}' больше не доступен"
            if item.product.stock < item.quantity:
                return False, f"Недостаточно товара '{item.product.name}'"
        
        return True, "Корзина готова к оформлению"