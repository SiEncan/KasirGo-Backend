from django.db import models
import uuid

# Create your models here.
# class User(models.Model):
#   name = models.CharField(max_length=100)
#   email = models.EmailField()
#   password = models.CharField(max_length=100)

#   def __str__(self):
#     return self.name

from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class User(AbstractUser):
    """Custom User untuk kasir/staff"""
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('cashier', 'Kasir'),
        ('manager', 'Manager'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cashier')
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
    
    class Meta:
        db_table = "users"

class Category(models.Model):
    """Kategori produk: Minuman, Makanan, Snack, dll"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "category"
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    """Produk yang dijual di cafe"""
    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Harga modal
    stock = models.IntegerField(default=0)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    sku = models.CharField(max_length=50, unique=True, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product"
        ordering = ['name']

    def __str__(self):
        return self.name


class Transaction(models.Model):
    """Transaksi penjualan"""
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('bca va', 'BCA VA'),
        ('qris', 'QRIS'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    ORDER_TYPE_CHOICES = [
        ('dine_in', 'Dine In'),
        ('take_away', 'Take Away'),
    ]

    transaction_number = models.CharField(max_length=50, unique=True, editable=False)
    cashier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='transactions')
    customer_name = models.CharField(max_length=100, blank=True, null=True)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default='dine_in')
    
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2)
    change_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "transaction"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.transaction_number:
            # Generate nomor transaksi otomatis: TRX-20231225-001
            today = timezone.now().strftime('%Y%m%d')
            last_transaction = Transaction.objects.filter(
                transaction_number__startswith=f'TRX-{today}'
            ).order_by('-transaction_number').first()
            
            if last_transaction:
                last_number = int(last_transaction.transaction_number.split('-')[-1])
                new_number = last_number + 1
            else:
                new_number = 1
            
            self.transaction_number = f'TRX-{today}-{new_number:03d}'
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transaction_number} - Rp {self.total}"


class TransactionItem(models.Model):
    """Detail item dalam transaksi"""
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=200)  # Simpan nama untuk history
    quantity = models.IntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)  # Harga saat transaksi
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True)  # Catatan khusus item
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"
    
    class Meta:
        db_table = "transaction_item"


class Payment(models.Model):
    """Payment record untuk integrasi Duitku"""
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='payments')
    merchant_order_id = models.CharField(max_length=100, unique=True)  # Order ID untuk Duitku
    reference = models.CharField(max_length=100, blank=True, null=True)  # Reference dari Duitku
    payment_url = models.URLField(blank=True, null=True)  # URL pembayaran QRIS/VA
    va_number = models.CharField(max_length=50, blank=True, null=True)  # Virtual Account number
    qr_string = models.TextField(blank=True, null=True)  # QR String untuk QRIS
    payment_method = models.CharField(max_length=20)  # SP (QRIS), VC (Visa), etc
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    status_code = models.CharField(max_length=10, blank=True, null=True)  # Status code dari Duitku
    status_message = models.TextField(blank=True, null=True)  # Message dari Duitku
    callback_data = models.JSONField(blank=True, null=True)  # Raw callback data
    expired_at = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.merchant_order_id} - {self.status}"