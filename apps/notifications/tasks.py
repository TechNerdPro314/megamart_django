from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_email_notification_task(self, notification_id: int) -> bool:
    """
    Асинхронная задача отправки email уведомления
    
    Args:
        notification_id: ID уведомления из БД
        
    Returns:
        bool: Успешно ли отправлено
    """
    from apps.notifications.models import Notification
    from apps.orders.models import Order
    
    try:
        notification = Notification.objects.select_related("order", "recipient").get(
            id=notification_id
        )
        
        # Получаем данные для отправки
        recipient_email = notification.recipient_email
        subject = notification.subject
        message = notification.message
        
        # Если есть связанный заказ - рендерим шаблон
        if notification.order:
            order = notification.order
            if notification.notification_type == "order_confirmation":
                html_message = render_to_string("emails/order_customer.html", {
                    "order": order,
                    "customer_name": notification.recipient.username if notification.recipient else recipient_email.split("@")[0],
                })
            elif notification.notification_type == "manager_alert":
                html_message = render_to_string("emails/order_manager.html", {
                    "order": order,
                })
            elif notification.notification_type == "status_update":
                html_message = render_to_string("emails/order_status.html", {
                    "order": order,
                    "customer_name": notification.recipient.username if notification.recipient else recipient_email.split("@")[0],
                    "new_status": order.get_status_display(),
                })
            else:
                html_message = message
            
            plain_message = strip_tags(html_message)
        else:
            html_message = message
            plain_message = strip_tags(html_message)
        
        # Отправляем email
        send_mail(
            subject=subject,
            message=plain_message,
            html_message=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        
        # Помечаем как отправленное
        notification.mark_sent()
        logger.info(f"Email уведомление {notification_id} отправлено успешно")
        return True
        
    except Notification.DoesNotExist:
        logger.error(f"Уведомление {notification_id} не найдено")
        return False
    except Exception as exc:
        logger.error(f"Ошибка отправки email уведомления {notification_id}: {exc}")
        
        # Повторная попытка с экспоненциальной задержкой
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def send_order_confirmation_email(order_id: int) -> bool:
    """
    Отправить подтверждение заказа клиенту (прямой вызов)
    
    Args:
        order_id: ID заказа
        
    Returns:
        bool: Успешно ли отправлено
    """
    from apps.notifications.services import EmailNotificationService
    from apps.orders.models import Order
    
    try:
        order = Order.objects.get(id=order_id)
        return EmailNotificationService.send_order_confirmation(order)
    except Order.DoesNotExist:
        logger.error(f"Заказ {order_id} не найден")
        return False


@shared_task
def send_manager_alert_email(order_id: int) -> bool:
    """
    Отправить уведомление менеджеру о новом заказе (прямой вызов)
    
    Args:
        order_id: ID заказа
        
    Returns:
        bool: Успешно ли отправлено
    """
    from apps.notifications.services import EmailNotificationService
    from apps.orders.models import Order
    
    try:
        order = Order.objects.get(id=order_id)
        return EmailNotificationService.send_manager_alert(order)
    except Order.DoesNotExist:
        logger.error(f"Заказ {order_id} не найден")
        return False


@shared_task
def send_status_update_email(order_id: int, new_status: str) -> bool:
    """
    Отправить уведомление об изменении статуса заказа
    
    Args:
        order_id: ID заказа
        new_status: Новый статус
        
    Returns:
        bool: Успешно ли отправлено
    """
    from apps.notifications.services import EmailNotificationService
    from apps.orders.models import Order
    
    try:
        order = Order.objects.get(id=order_id)
        return EmailNotificationService.send_status_update(order, new_status)
    except Order.DoesNotExist:
        logger.error(f"Заказ {order_id} не найден")
        return False


@shared_task
def send_bulk_notifications(limit: int = 100) -> int:
    """
    Обработать пакет уведомлений (для Celery Beat)
    
    Args:
        limit: Максимальное количество уведомлений за раз
        
    Returns:
        int: Количество обработанных уведомлений
    """
    from apps.notifications.services import NotificationManager
    
    count = NotificationManager.process_pending_notifications()
    logger.info(f"Обработано {count} уведомлений")
    return count
