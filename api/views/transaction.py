from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import hashlib
import requests
from api.utils_transaction import restore_stock, cleanup_expired_transactions

from api.models import Transaction, Payment
from api.serializer import TransactionSerializer, PaymentSerializer, CreatePaymentSerializer


@api_view(['POST'])
@transaction.atomic  # Rollback kalau error
def create_transaction(request):
  """
  Membuat transaksi baru
  POST /api/transactions/
  """
  serializer = TransactionSerializer(data=request.data, context={'request': request})
  if serializer.is_valid():
    transaction = serializer.save()
    
    return Response({
      'message': 'Transaction has been created',
      'data': TransactionSerializer(transaction).data
    }, status=status.HTTP_201_CREATED)
  
  return Response({
    'message': 'Failed to create transaction',
    'errors': serializer.errors
  }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PATCH', 'DELETE'])
def get_update_delete_transaction(request, transaction_id):
  """
  Mendapatkan, mengupdate, atau menghapus transaksi berdasarkan ID
  """
  if request.method == 'GET':
    try:
      transaction = Transaction.objects.get(id=transaction_id, cafe=request.user.cafe)
    except Transaction.DoesNotExist:
      return Response({ 'message': "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = TransactionSerializer(transaction)
    return Response({'message:': 'Success', 'data': serializer.data}, status=status.HTTP_200_OK)
  elif request.method == 'PATCH':
    try:
      transaction = Transaction.objects.get(id=transaction_id, cafe=request.user.cafe)
    except Transaction.DoesNotExist:
      return Response({ 'message': "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = TransactionSerializer(transaction, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()

    return Response({
      'message': 'Transaction has been updated',
      'data': serializer.data
      }, status=status.HTTP_200_OK)

  elif request.method == 'DELETE':    
    try:
      transaction = Transaction.objects.get(id=transaction_id, cafe=request.user.cafe)
    except Transaction.DoesNotExist:
      return Response({ 'message': "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)

    transaction.delete()

    return Response({
      'message': 'Transaction has been deleted/voided and stock restored',
    }, status=status.HTTP_200_OK)
    
@api_view(['GET'])
def list_transactions(request):
  """
  Mendapatkan daftar transaksi dengan filter tanggal dan pagination
  GET /api/transaction/?start_date=2025-12-01&end_date=2025-12-07&page=2&page_size=10
  """
  # === LAZY UPDATE EXPIRED TRANSACTIONS ===
  if request.user.cafe:
    cleanup_expired_transactions(request.user.cafe)

  # ========================================

  # Base Filter: Tenant Isolation
  transactions = Transaction.objects.filter(cafe=request.user.cafe)

  page = int(request.GET.get('page', 1))
  page_size = int(request.GET.get('page_size', 10))
  start = (page - 1) * page_size
  end = start + page_size

  # filter by date
  start_date = request.GET.get('start_date')
  end_date = request.GET.get('end_date')
  if start_date:
    transactions = transactions.filter(created_at__date__gte=start_date)
  if end_date:
    transactions = transactions.filter(created_at__date__lte=end_date)
      
  # filter by search query
  search_query = request.GET.get('search')
  if search_query:
    transactions = transactions.filter(
      Q(transaction_number__icontains=search_query) |
      Q(customer_name__icontains=search_query) |
      Q(notes__icontains=search_query)
    )

  # filter by status
  status_param = request.GET.get('status')
  if status_param:
    statuses = [s.strip() for s in status_param.split(',')]
    if len(statuses) == 1:
      transactions = transactions.filter(status=statuses[0])
    else:
      transactions = transactions.filter(status__in=statuses)

  # slicing
  transactions_page = transactions[start:end]
  total_page = transactions.count()

  serializer = TransactionSerializer(transactions_page, many=True)

  return Response({
    'message': 'Success',
    'total_page': total_page,
    'page': page,
    'page_size': page_size,
    'data': serializer.data
  })


# ==================== PAYMENT (DUITKU) ENDPOINTS ====================
@api_view(['POST'])
@transaction.atomic
def create_payment(request):
  """
  Membuat pembayaran baru via Duitku
  POST /api/payment/create/
  """
  serializer = CreatePaymentSerializer(data=request.data)
  serializer.is_valid(raise_exception=True)
  data = serializer.validated_data
  
  # Get transaction
  try:
    trx = Transaction.objects.get(id=data['transaction_id'], cafe=request.user.cafe) # Secured
  except Transaction.DoesNotExist:
    return Response({
      'message': 'Transaction not found'
    }, status=status.HTTP_404_NOT_FOUND)
  
  # Check if transaction already has successful payment
  existing_payment = Payment.objects.filter(
      transaction=trx,
      status='success'
  ).first()
  if existing_payment:
    return Response({
      'message': 'Transaction already paid',
      'data': PaymentSerializer(existing_payment).data
    }, status=status.HTTP_400_BAD_REQUEST)
  
  # Duitku configuration 
  # FUTURE: Use request.user.cafe.payment_config instead of Settings
  merchant_code = settings.DUITKU_MERCHANT_CODE
  api_key = settings.DUITKU_API_KEY
  is_sandbox = settings.DUITKU_IS_SANDBOX
  callback_url = settings.DUITKU_CALLBACK_URL
  return_url = settings.DUITKU_RETURN_URL
  
  if not merchant_code:
    return Response({
      'message': 'Duitku Merchant Code not configured'
    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
  
  # Generate unique merchant order ID (Use Cafe Prefix?)
  # merchant_order_id = f"PAY-{trx.transaction_number}-{timezone.now().strftime('%H%M%S')}"
  # For safe multi-tenancy, maybe prepend Cafe ID?
  merchant_order_id = f"{request.user.cafe.id}-{trx.transaction_number}-{timezone.now().strftime('%H%M%S')}"
  
  amount = int(trx.total)
  payment_method = data.get('payment_method', 'SP')
  
  # Generate signature
  signature = hashlib.md5(f"{merchant_code}{merchant_order_id}{amount}{api_key}".encode()).hexdigest()
  
  # Prepare request to Duitku
  base_url = "https://sandbox.duitku.com" if is_sandbox else "https://passport.duitku.com"
  endpoint = f"{base_url}/webapi/api/merchant/v2/inquiry"
  
  customer_name = trx.customer_name or "Customer"
  customer_email = "customer@kasirgo.com"
  
  payload = {
    "merchantCode": merchant_code,
    "paymentAmount": amount,
    "paymentMethod": payment_method,
    "merchantOrderId": merchant_order_id,
    "productDetails": f"Pembayaran {trx.transaction_number}",
    "customerVaName": customer_name,
    "email": customer_email,
    "phoneNumber": "08123456789",
    "itemDetails": [
      {
        "name": f"Order {trx.transaction_number}",
        "price": amount,
        "quantity": 1
      }
    ],
    "customerDetail": {
      "firstName": customer_name,
      "lastName": "",
      "email": customer_email,
      "phoneNumber": "08123456789"
    },
    "callbackUrl": callback_url,
    "returnUrl": return_url,
    "signature": signature,
    "expiryPeriod": 60 
  }
  
  headers = {
    "Content-Type": "application/json"
  }
  
  try:
    response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
    response_data = response.json()
    
    if response.status_code == 200 and response_data.get('statusCode') == '00':
      # Success - create payment record
      expired_at = timezone.now() + timedelta(minutes=60)
      
      payment = Payment.objects.create(
        transaction=trx,
        merchant_order_id=merchant_order_id,
        reference=response_data.get('reference', ''),
        payment_url=response_data.get('paymentUrl', ''),
        va_number=response_data.get('vaNumber', ''),
        qr_string=response_data.get('qrString', ''),
        payment_method=payment_method,
        amount=amount,
        status='pending',
        status_code=response_data.get('statusCode'),
        status_message=response_data.get('statusMessage'),
        expired_at=expired_at
      )
      
      return Response({
        'message': 'Payment created successfully',
        'data': {
          'payment_id': payment.id,
          'transaction_id': trx.id,
          'merchant_order_id': merchant_order_id,
          'reference': response_data.get('reference'),
          'payment_url': response_data.get('paymentUrl'),
          'va_number': response_data.get('vaNumber'),
          'qr_string': response_data.get('qrString'),
          'amount': amount,
          'expired_at': expired_at.isoformat()
        }
      }, status=status.HTTP_201_CREATED)
    else:
      return Response({
        'message': response_data.get('Message', 'Unknown error'),
        'status_code': response_data.get('statusCode')
      }, status=status.HTTP_400_BAD_REQUEST)
          
  except requests.exceptions.RequestException as e:
    return Response({
      'message': 'Failed to connect to payment gateway',
      'error': str(e)
    }, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def payment_callback(request):
  """
  Webhook callback dari Duitku
  """
  try:
    if request.content_type == 'application/json':
      callback_data = request.data
    else:
      callback_data = request.POST.dict()
    
    merchant_order_id = callback_data.get('merchantOrderId')
    result_code = callback_data.get('resultCode')
    amount = callback_data.get('amount')
    signature = callback_data.get('signature')
    reference = callback_data.get('reference')
    
    if not merchant_order_id:
      return Response({
        'message': 'Invalid callback data'
      }, status=status.HTTP_400_BAD_REQUEST)
    
    # Verify signature
    # Future: Verify per-cafe Merchant Code
    merchant_code = settings.DUITKU_MERCHANT_CODE
    api_key = settings.DUITKU_API_KEY
    expected_signature = hashlib.md5(
      f"{merchant_code}{amount}{merchant_order_id}{api_key}".encode()
    ).hexdigest()
    
    if signature != expected_signature:
      return Response({
        'message': 'Invalid signature'
      }, status=status.HTTP_403_FORBIDDEN)
    
    try:
      payment = Payment.objects.get(merchant_order_id=merchant_order_id)
    except Payment.DoesNotExist:
      return Response({
        'message': 'Payment not found'
      }, status=status.HTTP_404_NOT_FOUND)
    
    # Update payment status
    payment.callback_data = callback_data
    payment.reference = reference or payment.reference
    
    if result_code == '00':
      payment.status = 'success'
      payment.paid_at = timezone.now()
      
      payment.transaction.status = 'completed'
      payment.transaction.save()
    elif result_code == '01':
      payment.status = 'pending'
    else:
      payment.status = 'failed'
      if payment.transaction.status != 'cancelled':
        restore_stock(payment.transaction)
        payment.transaction.status = 'cancelled'
        payment.transaction.save()
    
    payment.status_code = result_code
    payment.save()
    
    return Response({
      'message': 'Callback processed successfully'
    }, status=status.HTTP_200_OK)
      
  except Exception as e:
    return Response({
      'message': 'Error processing callback',
      'error': str(e)
    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_payment_status(request, payment_id):
  """
  Cek status pembayaran
  """
  try:
    # Securely get payment scoped to user's cafe
    payment = Payment.objects.get(id=payment_id, transaction__cafe=request.user.cafe)
             
  except Payment.DoesNotExist:
    return Response({
      'message': 'Payment not found'
    }, status=status.HTTP_404_NOT_FOUND)
  
  check_realtime = request.GET.get('realtime', 'false').lower() == 'true'
  
  if check_realtime and payment.status == 'pending':
    merchant_code = settings.DUITKU_MERCHANT_CODE
    api_key = settings.DUITKU_API_KEY
    is_sandbox = settings.DUITKU_IS_SANDBOX
    
    signature = hashlib.md5(
      f"{merchant_code}{payment.merchant_order_id}{api_key}".encode()
    ).hexdigest()
    
    base_url = "https://sandbox.duitku.com" if is_sandbox else "https://passport.duitku.com"
    endpoint = f"{base_url}/webapi/api/merchant/transactionStatus"
    
    payload = {
      "merchantCode": merchant_code,
      "merchantOrderId": payment.merchant_order_id,
      "signature": signature
    }
    
    try:
      response = requests.post(endpoint, json=payload, timeout=30)
      response_data = response.json()
      
      if response_data.get('statusCode') == '00':
        payment.status = 'success'
        payment.paid_at = timezone.now()
        payment.transaction.status = 'completed'
        payment.transaction.save()
      elif response_data.get('statusCode') == '01':
        payment.status = 'pending'
      elif response_data.get('statusCode') == '02':
        payment.status = 'cancelled'
        payment.transaction.status = 'cancelled'
        payment.transaction.save()
      else:
        payment.status = 'expired'
        payment.transaction.status = 'cancelled'
        payment.transaction.save()
      
      payment.status_code = response_data.get('statusCode')
      payment.status_message = response_data.get('statusMessage')
      payment.save()
        
    except requests.exceptions.RequestException:
      pass 
  
  return Response({
    'message': 'Success',
    'data': PaymentSerializer(payment).data
  }, status=status.HTTP_200_OK)


@api_view(['POST'])
@transaction.atomic
def cancel_transaction(request, transaction_id):
  """
  Membatalkan transaksi secara manual
  """
  try:
    trx = Transaction.objects.get(id=transaction_id, cafe=request.user.cafe)
  except Transaction.DoesNotExist:
    return Response({'message': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)

  if trx.status == 'completed':
    return Response({'message': 'Cannot cancel completed transaction'}, status=status.HTTP_400_BAD_REQUEST)

  if trx.status == 'cancelled':
    return Response({'message': 'Transaction is already cancelled'}, status=status.HTTP_400_BAD_REQUEST)

  # Cancel transaction
  restore_stock(trx)
  trx.status = 'cancelled'
  trx.save()

  # Cancel associated pending payments
  pending_payments = Payment.objects.filter(transaction=trx, status='pending')
  for payment in pending_payments:
    payment.status = 'cancelled'
    payment.save()

  return Response({
    'message': 'Transaction has been cancelled',
    'data': TransactionSerializer(trx).data
  }, status=status.HTTP_200_OK)
