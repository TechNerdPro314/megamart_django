from django import forms
from .models import Order

def validate_address(value):
    """Проверяет, что адрес содержит и буквы, и цифры, и имеет длину не менее 10 символов."""
    if len(value.strip()) < 10:
        raise forms.ValidationError("Адрес должен быть не менее 10 символов.")
    if not any(ch.isalpha() for ch in value):
        raise forms.ValidationError("Адрес должен содержать название улицы (буквы).")
    if not any(ch.isdigit() for ch in value):
        raise forms.ValidationError("Адрес должен содержать номер дома (цифры).")

class CheckoutForm(forms.ModelForm):
    # Валидатор убран, проверка в clean_customer_phone
    customer_phone = forms.CharField(
        max_length=18,
        widget=forms.TextInput(attrs={
            'type': 'tel',
            'class': 'phone-mask',
            'placeholder': '+7 (___) ___-__-__'
        })
    )
    delivery_address = forms.CharField(
        required=True,
        validators=[validate_address],
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Город, улица, дом, квартира (например, г. Москва, ул. Тверская, д. 15, кв. 7)',
            'class': 'form-control',
        })
    )
    delivery_method = forms.CharField(widget=forms.HiddenInput(), required=True)

    class Meta:
        model = Order
        fields = [
            'customer_name',
            'customer_email',
            'customer_phone',
            'delivery_address',
            'comment',
        ]

    def clean_customer_phone(self):
        phone = self.cleaned_data.get('customer_phone', '')
        # Убираем всё, кроме цифр
        digits = ''.join(ch for ch in phone if ch.isdigit())
        # Проверяем, что номер начинается с 7 или 8 и содержит 11 цифр
        if len(digits) != 11 or digits[0] not in ('7', '8'):
            raise forms.ValidationError("Некорректный номер телефона.")
        # Возвращаем только цифры (можно преобразовать 8 в 7 при необходимости)
        return digits

    def clean_delivery_method(self):
        method = self.cleaned_data['delivery_method']
        from apps.cart.services import DELIVERY_OPTIONS
        if method not in DELIVERY_OPTIONS:
            raise forms.ValidationError("Выберите способ доставки")
        return method