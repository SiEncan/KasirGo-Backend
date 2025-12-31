from django.utils import timezone
from api.models import Transaction, Payment

def restore_stock(transaction):
  """
  Helper untuk mengembalikan stok produk saat transaksi dibatalkan.
  """
  for item in transaction.items.all():
    product = item.product
    product.stock += item.quantity
    product.save()

def cleanup_expired_transactions(cafe):
  """
  Cari pembayaran yang statusnya pending DAN sudah lewat waktu expirednya.
  Restore stock dan set status jadi cancelled/expired.
  """
  now = timezone.now()
  
  query = Payment.objects.filter(
    status='pending',
    expired_at__lt=now
  )
  
  # Filter by cafe strictly to enforce multi-tenancy
  query = query.filter(transaction__cafe=cafe)
  
  expired_payments_qs = query
  
  if expired_payments_qs.exists():
    # Ambil transaksi yang terkait
    expired_trx_ids = list(expired_payments_qs.values_list('transaction_id', flat=True))
    expired_transactions = Transaction.objects.filter(id__in=expired_trx_ids)
    
    # 1. Restore Stock for EACH transaction
    for trx in expired_transactions:
      if trx.status != 'cancelled':
        restore_stock(trx)
    
    # 2. Update status Payment jadi 'expired'
    expired_payments_qs.update(status='expired')
    
    # 3. Update status Transaction jadi 'cancelled'
    Transaction.objects.filter(id__in=expired_trx_ids).update(status='cancelled')
    
    return len(expired_trx_ids)
  return 0
