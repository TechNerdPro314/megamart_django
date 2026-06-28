from celery import shared_task
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


@shared_task
def send_order_notifications(order_id: int):
    """
    Отправить все уведомления после создания заказа
    
    1. Подтверждение клиенту
    2. Уведомление менеджеру
    
    Args:
        order_id: ID заказа
    """
    from apps.orders.models import Order
    from apps.notifications.services import EmailNotificationService
    from apps.notifications.models import Notification
    
    try:
        order = Order.objects.select_related("user").get(id=order_id)
        
        # 1. Подтверждение клиенту
        client_sent = EmailNotificationService.send_order_confirmation(order)
        
        # Создаем запись в истории уведомлений
        Notification.objects.create(
            notification_type="order_confirmation",
            recipient=order.user,
            recipient_email=order.customer_email,
            order=order,
            subject=f"Заказ #{order.id} подтвержден",
            message=f"Ваш заказ #{order.id} успешно оформлен",
            status="sent" if client_sent else "failed",
            sent_at=timezone.now() if client_sent else None,
        )
        
        if client_sent:
            logger.info(f"Подтверждение заказа #{order.id} отправлено клиенту")
        else:
            logger.error(f"Не удалось отправить подтверждение заказа #{order.id}")
        
        # 2. Уведомление менеджеру
        manager_sent = EmailNotificationService.send_manager_alert(order)
        
        # Создаем запись в истории уведомлений
        Notification.objects.create(
            notification_type="manager_alert",
            recipient_email=getattr(settings, "MANAGER_EMAILS", ["manager@megamart.com"])[0],
            order=order,
            subject=f"Новый заказ #{order.id}",
            message=f"Новый заказ от {order.customer_name}",
            status="sent" if manager_sent else "failed",
            sent_at=timezone.now() if manager_sent else None,
        )
        
        if manager_sent:
            logger.info(f"Уведомление о заказе #{order.id} отправлено менеджеру")
        else:
            logger.error(f"Не удалось отправить уведомление о заказе #{order.id}")
        
        return {
            "client_sent": client_sent,
            "manager_sent": manager_sent,
        }
        
    except Order.DoesNotExist:
        logger.error(f"Заказ {order_id} не найден")
        return {"error": "Order not found"}
    except Exception as e:
        logger.error(f"Ошибка отправки уведомлений для заказа {order_id}: {e}")
        return {"error": str(e)}


@shared_task
def send_status_update_notification(order_id: int, new_status: str):
    """
    Отправить уведомление об изменении статуса заказа
    
    Args:
        order_id: ID заказа
        new_status: Новый статус
    """
    from apps.orders.models import Order
    from apps.notifications.services import EmailNotificationService
    from apps.notifications.models import Notification
    
    try:
        order = Order.objects.select_related("user").get(id=order_id)
        
        sent = EmailNotificationService.send_status_update(order, new_status)
        
        Notification.objects.create(
            notification_type="status_update",
            recipient=order.user,
            recipient_email=order.customer_email,
            order=order,
            subject=f"Статус заказа #{order.id} изменен",
            message=f"Ваш заказ #{order.id} теперь имеет статус: {order.get_status_display()}",
            status="sent" if sent else "failed",
            sent_at=timezone.now() if sent else None,
        )
        
        return {"sent": sent}
        
    except Order.DoesNotExist:
        logger.error(f"Заказ {order_id} не найден")
        return {"error": "Order not found"}
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о статусе {order_id}: {e}")
        return {"error": str(e)}
