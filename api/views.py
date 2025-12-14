from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from .models import User, Product, Transaction
from .serializer import UserSerializer, CreateUserSerializer, CategorySerializer, ProductSerializer, \
  TransactionSerializer
from django.db import connection, transaction
from django.db.models import Q
from django.contrib.auth.hashers import make_password, check_password
import uuid

class LogoutView(APIView):
  """
  Logout user dengan blacklisting refresh token
  POST /api/auth/logout/
  Body: {
    "refresh": "refresh_token_here"
  }
  """
  def post(self, request):
    refresh_token = request.data.get("refresh")
    if not refresh_token:
        return Response({"error": "Refresh token required"}, status=400)
    try:

      # Parse token untuk cek siapa owner-nya
      token_obj = RefreshToken(refresh_token)
      token_user_id = str(token_obj['user_id'])  # user_id di token

      if token_user_id != str(request.user.id):
        return Response({"error": "Tidak bisa logout token user lain"}, status=403)

      token_obj.blacklist()  # invalidate token
      return Response({"message": "Logout berhasil"}, status=status.HTTP_205_RESET_CONTENT)
    except (TokenError, InvalidToken) as e:
      return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)
      
@api_view(['GET'])
def get_all_users(request):
  """
  Mendapatkan semua user
  GET /api/users/
  """
  if request.user.role != 'admin':
    return Response({
      'message': 'Anda tidak memiliki izin untuk mengakses data ini'
    }, status=status.HTTP_403_FORBIDDEN)

  with connection.cursor() as cursor:
    cursor.execute("SELECT id, username, email, first_name, last_name, role, phone, is_active, date_joined, last_login FROM users \
                  ORDER BY date_joined DESC")

    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]
    result = [dict(zip(columns, row)) for row in rows]

  return Response({'message:': 'Success', 'data': result}, status=status.HTTP_200_OK)

@api_view(['POST'])
@transaction.atomic
@permission_classes([AllowAny])
def create_user(request):
  """
  Membuat user baru
  POST /api/users/create/
  Body: {
    "first_name": "John",
    "last_name": "Doe",
    "username": "johndoe",
    "email": "johndoe@example.com",
    "role": "cashier",
    "phone": "08123456789",
    "password": "password123"
  }
  """
  serializer = CreateUserSerializer(data=request.data)
  serializer.is_valid(raise_exception=True)
  data = serializer.validated_data

  first_name = data.get('first_name')
  last_name = data.get('last_name')
  username = data.get('username')
  email = data.get('email')
  role = data.get('role', 'cashier')
  phone = data.get('phone', '')
  password = data.get('password')
  new_id = str(uuid.uuid4())

  with connection.cursor() as cursor: # auto close cursor
    # Cek username sudah ada atau belum
    cursor.execute('SELECT id FROM users WHERE username = %s', [username])
    if cursor.fetchone():
        return Response({
            'message': 'Username sudah digunakan'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Cek email sudah ada atau belum
    cursor.execute('SELECT id FROM users WHERE email = %s', [email])
    if cursor.fetchone():
        return Response({
            'message': 'Email sudah digunakan'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # hash password
    hashed_password = make_password(password)

    # Set is_staff based on role
    is_staff = True if role == 'admin' else False
    
    cursor.execute("INSERT INTO users (id, first_name, last_name, username, email, role, phone, " \
                  "is_active, is_superuser, is_staff, password, date_joined, updated_at, created_at, last_login) " \
                  "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW(), NULL)" \
                  "RETURNING first_name, last_name, username, email, role, phone", 
                  [new_id,first_name, last_name, username, email, role, phone, True, False, is_staff, hashed_password])
    
    # Ambil data user yang baru dibuat
    columns = [col[0] for col in cursor.description]
    user_data = dict(zip(columns, cursor.fetchone()))

  return Response({
      'message': 'User has been created', 
      'data': user_data
    }, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@transaction.atomic
def change_password(request, user_id):
    """
    Change password dengan verifikasi password lama
    POST /api/users/<user_id>/change-password/
    Body: {
      "old_password": "password123",
      "new_password": "newpassword456"
    }
    """

    if user_id != request.user.id and not request.user.role == 'admin':
      return Response({
        'message': 'Anda tidak memiliki izin untuk mengakses data ini'
      }, status=status.HTTP_403_FORBIDDEN)

    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')
    
    # Validasi
    if not old_password or not new_password:
      return Response({
        'message': 'Password lama dan baru wajib diisi'
      }, status=status.HTTP_400_BAD_REQUEST)
    
    if len(new_password) < 8:
      return Response({
        'message': 'Password minimal 8 karakter'
      }, status=status.HTTP_400_BAD_REQUEST)
    
    with connection.cursor() as cursor:
      # Ambil password lama dari database
      cursor.execute(
        'SELECT password FROM users WHERE id = %s', 
        [user_id]
      )
      row = cursor.fetchone()
      db_old_password = row[0] # karena bentuk tuple, jadi harus ambil index 0
      
      if not db_old_password:
        return Response({
          'message': 'User tidak ditemukan'
        }, status=status.HTTP_404_NOT_FOUND)
      
      # Verifikasi password lama
      if not check_password(old_password, db_old_password):
        return Response({
          'message': 'Password lama salah'
        }, status=status.HTTP_400_BAD_REQUEST)
      
      # Hash password baru
      new_hashed_password = make_password(new_password)
      
      # Update password
      cursor.execute("""
        UPDATE users 
        SET password = %s, updated_at = NOW()
        WHERE id = %s
      """, [new_hashed_password, user_id])
    
    return Response({
      'message': 'Password berhasil diubah'
    }, status=status.HTTP_200_OK)

@api_view(['GET', 'PATCH', 'DELETE'])
def get_update_delete_user(request, user_id):
  """
  Mendapatkan, mengupdate, atau menghapus user berdasarkan ID
  GET /api/user/<user_id>/
  PATCH /api/user/<user_id>/
  DELETE /api/user/<user_id>/
  """
  if user_id != request.user.id and not request.user.role == 'admin':
    return Response({
      'message': 'Anda tidak memiliki izin untuk mengakses data ini'
    }, status=status.HTTP_403_FORBIDDEN)
  
  if request.method == 'GET':

    with connection.cursor() as cursor:
      cursor.execute("SELECT username, email, first_name, last_name, role, phone, is_active, date_joined, last_login \
      FROM users WHERE id = %s", (user_id,))

      user = cursor.fetchone()
      if not user:
        return Response({'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
      
      columns = [col[0] for col in cursor.description]
      user_data = dict(zip(columns, user))

    return Response({'message': 'Success', 'data': user_data}, status=status.HTTP_200_OK)
  
  elif request.method == 'PATCH':
    first_name = request.data.get('first_name')
    last_name = request.data.get('last_name')
    username = request.data.get('username')
    email = request.data.get('email')
    role = request.data.get('role')
    phone = request.data.get('phone')

    updates = []
    params = []
    
    if first_name is not None:
      updates.append('first_name = %s')
      params.append(first_name)
    
    if last_name is not None:
      updates.append('last_name = %s')
      params.append(last_name)
    
    if username is not None:
      updates.append('username = %s')
      params.append(username)
    
    if email is not None:
      updates.append('email = %s')
      params.append(email)
    
    if role is not None:
      updates.append('role = %s')
      params.append(role)
    
    if phone is not None:
      updates.append('phone = %s')
      params.append(phone)
    
    updates.append('updated_at = NOW()')

    if len(params) == 0:
      return Response({
        'message': 'Tidak ada data yang diupdate'
      }, status=status.HTTP_400_BAD_REQUEST)
    
    params.append(user_id)

    sql = f"""
          UPDATE users 
          SET {', '.join(updates)}
          WHERE id = %s
          RETURNING first_name, last_name, username, email, role, phone
        """

    with connection.cursor() as cursor:
      cursor.execute("SELECT id FROM users WHERE id = %s", [user_id])
      if not cursor.fetchone():
        return Response({
          'message': 'User tidak ditemukan'
        }, status = status.HTTP_404_NOT_FOUND)
      
      cursor.execute(sql, params)

      columns = [col[0] for col in cursor.description]
      user_data = dict(zip(columns, cursor.fetchone()))

    return Response({
        'message': 'User berhasil diupdate',
        'data': user_data
    }, status=status.HTTP_200_OK)
  
  elif request.method == 'DELETE':
    with connection.cursor() as cursor:
      cursor.execute(f"SELECT id FROM users WHERE id = {user_id}")
      if not cursor.fetchone():
        return Response({
          'message': 'User tidak ditemukan'
        }, status = status.HTTP_404_NOT_FOUND)
      
      cursor.execute(f"DELETE FROM users WHERE id = {user_id}")
    
    return Response({
      'message': 'User berhasil dihapus'
    }, status=status.HTTP_200_OK)
  

@api_view(['GET'])
def get_all_categories(request):
  """
  Mendapatkan semua kategori produk
  GET /api/category/
  """
  with connection.cursor() as cursor:
    cursor.execute("SELECT id, name, description, created_at, updated_at FROM category ORDER BY created_at DESC")
    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]
    result = [dict(zip(columns, row)) for row in rows]

  return Response({'message:': 'Success', 'data': result}, status=status.HTTP_200_OK)

@api_view(['GET', 'PATCH', 'DELETE'])
def get_update_delete_category(request, category_id):
  """
  Mendapatkan, mengupdate, atau menghapus kategori produk berdasarkan ID
  GET /api/category/<category_id>/
  PATCH /api/category/<category_id>/
  DELETE /api/category/<category_id>/
  """
  if request.method == 'GET':
    with connection.cursor() as cursor:
      cursor.execute("SELECT name, description, created_at, updated_at FROM category WHERE id = %s", [category_id])
      row = cursor.fetchone()
      if not row:
        return Response({'message': 'Category not found'}, status=status.HTTP_404_NOT_FOUND)
      
      columns = [col[0] for col in cursor.description]
      category_data = dict(zip(columns, row))

    return Response({'message:': 'Success', 'data': category_data}, status=status.HTTP_200_OK)

  elif request.method == 'PATCH':
    name = request.data.get('name')
    description = request.data.get('description')

    updates = []
    params = []

    if name is not None:
      updates.append('name = %s')
      params.append(name)
    
    if description is not None:
      updates.append('description = %s')
      params.append(description)
    
    updates.append('updated_at = NOW()')

    with connection.cursor() as cursor:
      cursor.execute("SELECT id FROM category WHERE id = %s", [category_id])
      if not cursor.fetchone():
        return Response({'message': 'Category not found'}, status=status.HTTP_404_NOT_FOUND)
      
      if len(params) == 0:
        return Response({
          'message': 'Tidak ada data yang diupdate'
        }, status=status.HTTP_400_BAD_REQUEST)
      
      params.append(category_id)

      sql = f"""
            UPDATE category 
            SET {', '.join(updates)}
            WHERE id = %s
            RETURNING name, description, created_at, updated_at
        """
      cursor.execute(sql, params)

      columns = [col[0] for col in cursor.description]
      category_data = dict(zip(columns, cursor.fetchone()))

    return Response({
        'message': 'Kategori produk berhasil diupdate',
        'data': category_data
    }, status=status.HTTP_200_OK)

  elif request.method == 'DELETE':
    with connection.cursor() as cursor:
      cursor.execute("SELECT id FROM category WHERE id = %s", [category_id])
      if not cursor.fetchone():
        return Response({'message': 'Category not found'}, status=status.HTTP_404_NOT_FOUND)
      
      cursor.execute("UPDATE product SET category_id = NULL WHERE category_id = %s", [category_id])
      
      cursor.execute("DELETE FROM category WHERE id = %s", [category_id])
    
    return Response({
      'message': 'Kategori produk berhasil dihapus'
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
def create_category(request):
  """
  Membuat kategori produk baru
  POST /api/category/create/
  Body: {
    "name": "Minuman",
    "description": "Kategori untuk semua jenis minuman"
  }
  """

  serializer = CategorySerializer(data=request.data)
  serializer.is_valid(raise_exception=True)
  data = serializer.validated_data

  name = data.get('name')
  description = data.get('description')

  with connection.cursor() as cursor:
    cursor.execute("""
      INSERT INTO category (name, description, created_at, updated_at)
      VALUES (%s, %s, NOW(), NOW())
      RETURNING name, description
    """, [name, description])

    columns = [col[0] for col in cursor.description]
    category_data = dict(zip(columns, cursor.fetchone()))
  
  return Response({
    'message': 'Kategori produk berhasil dibuat',
    'data': category_data
  }, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@transaction.atomic
def create_product(request):
  """
  Membuat produk baru
  POST /api/product/create/
  Body: {
    "name": "Es Teh",
    "description": "Minuman segar",
    "price": 5000,
    "cost": 3000,
    "stock": 100,
    "image": null,
    "is_available": true,
    "sku": "ES-TEH-001",
    "category": 1,
  }
  """
  serializer = ProductSerializer(data=request.data)
  serializer.is_valid(raise_exception=True)
  product = serializer.save()
  # data = serializer.validated_data

  # name = data.get('name')
  # description = data.get('description', '')
  # price = data.get('price')
  # cost = data.get('cost', 0)
  # stock = data.get('stock', 0)
  # category = data.get('category')
  # image = data.get('image', '')
  # is_available = data.get('is_available', True)
  # sku = data.get('sku', '')

  # Ambil ID dari Category object
  # category_id = category.id if category else None
  
  # with connection.cursor() as cursor:
  #   cursor.execute("""
  #     INSERT INTO product (
  #       name, description, price, cost, stock, 
  #       category_id, image, is_available, sku, 
  #       created_at, updated_at
  #     )
  #       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
  #       RETURNING id, name, description, price, cost, stock, 
  #       category_id, image, is_available, sku, created_at
  #     """, [name, description, price, cost, stock, 
  #     category_id, image, is_available, sku])
    
  #   columns = [col[0] for col in cursor.description]
  #   product_data = dict(zip(columns, cursor.fetchone()))

  return Response({
    'message': 'Produk berhasil dibuat',
    'data': ProductSerializer(product).data
  }, status=status.HTTP_201_CREATED)

# ################################           RAW QUERY                #########################################################################
# @api_view(['GET'])
# def search_products(request):
#   """
#   Mencari produk berdasarkan berbagai kriteria
#   GET /api/products/search/?name=kopi&category=2&min_price=5000&max_price=20000
#   """
#   name = request.GET.get('name', '')
#   category_id = request.GET.get('category', '')
#   min_price = request.GET.get('min_price', '')
#   max_price = request.GET.get('max_price', '')
#   is_available = request.GET.get('available', '')
  
#   query = []
#   params = []
#   if name:
#     query.append('LOWER(name) LIKE %s')
#     params.append(f"%{name.lower()}%")
  
#   if category_id:
#     query.append('category_id = %s')
#     params.append(category_id)

#   if min_price:
#     query.append('price >= %s')
#     params.append(min_price)

#   if max_price:
#     query.append('price <= %s')
#     params.append(max_price)

#   if is_available:
#     query.append('is_available = %s')
#     params.append(is_available)

#   where_sql = " AND ".join(query)
#   print(where_sql)

#   with connection.cursor() as cursor:

#     cursor.execute(f"SELECT * FROM product WHERE {where_sql}", params)
#     rows = cursor.fetchall()
#     columns = [col[0] for col in cursor.description]
#     result = [dict(zip(columns, row)) for row in rows]
  
#   return Response({
#     'message': 'success',
#     'data': result
#   }, status=status.HTTP_200_OK)

# ################################           ORM                #########################################################################
@api_view(['GET'])
def search_products(request):
  """
  Mencari produk berdasarkan berbagai kriteria
  GET /api/products/search/?name=kopi&category=2&min_price=5000&max_price=20000
  """

  name = request.GET.get('name', '')
  category_id = request.GET.get('category', '')
  min_price = request.GET.get('min_price', '')
  max_price = request.GET.get('max_price', '')
  is_available = request.GET.get('available', '')
  
  products = Product.objects.all()
  
  if name:
    products = products.filter(Q(name__icontains=name))
  if category_id:
    products = products.filter(category_id=category_id)
  if min_price:
    products = products.filter(price__gte=min_price)
  if max_price:
    products = products.filter(price__lte=max_price)
  if is_available:
    products = products.filter(is_available=is_available.lower() == 'true')
  
  # Serialize
  serializer = ProductSerializer(products, many=True)
  
  return Response({
    'message': 'Success',
    'count': products.count(),
    'data': serializer.data
  })

@api_view(['GET'])
def get_all_products(request):
  """
  Mendapatkan semua produk
  GET /api/products/
  """

  products = Product.objects.all()
  serializer = ProductSerializer(products, many=True)

  #   #  JOIN manual
  # with connection.cursor() as cursor:
  #   cursor.execute("""
  #       SELECT 
  #           p.id, p.name, p.price, p.category_id,
  #           c.name as category_name  -- ← JOIN untuk dapat nama
  #       FROM product p
  #       LEFT JOIN category c ON p.category_id = c.id
  #   """)
    
  #   rows = cursor.fetchall()
  #   columns = [col[0] for col in cursor.description]
  #   result = [dict(zip(columns, row)) for row in rows]

  return Response({'message:': 'Success', 'data': serializer.data}, status=status.HTTP_200_OK)


@api_view(['GET', 'PATCH', 'DELETE'])
def get_update_delete_product(request, product_id):
  """
  Mendapatkan, mengupdate, atau menghapus produk berdasarkan ID
  GET /api/product/<product_id>/
  PATCH /api/product/<product_id>/
  DELETE /api/product/<product_id>/
  """

  if request.method == 'GET':
    try:
      product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
      return Response({ 'message': "Product not found"}, status= status.HTTP_404_NOT_FOUND)

    result = ProductSerializer(product).data

    # with connection.cursor() as cursor:
    #   cursor.execute(f"SELECT * FROM product WHERE id = {product_id}")
    #   rows = cursor.fetchall()

    #   if not rows:
    #     return Response({ 'message': "Product not found"}, status= status.HTTP_404_NOT_FOUND)

    #   columns = [col[0] for col in cursor.description]
    #   result = [dict(zip(columns, row)) for row in rows]

    return Response({'message:': 'Success', 'data': result}, status=status.HTTP_200_OK)
  
  elif request.method == 'PATCH':
    try:
      product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
      return Response({ 'message': "Product not found"}, status= status.HTTP_404_NOT_FOUND)

    serializer = ProductSerializer(product, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()

    return Response({
      'message': 'Produk berhasil diupdate',
      'data': serializer.data
    }, status=status.HTTP_200_OK)
  
  elif request.method == 'DELETE':
    try:
      product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
      return Response({ 'message': "Product not found"}, status= status.HTTP_404_NOT_FOUND)

    product.delete()

    return Response({
      'message': 'Produk berhasil dihapus'
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
@transaction.atomic  # Rollback kalau error
def create_transaction(request):
    """
    Membuat transaksi baru
    POST /api/transactions/
    
    Body: {
      "payment_method": "cash",
      "paid_amount": 100000,
      "subtotal": 70000,
      "tax": 7000,
      "discount": 0,
      "total": 77000,
      "change_amount": 23000,
      "notes": "Catatan opsional",
      "items": [
        {
          "product": 1,
          "product_name": "Kopi Susu",
          "quantity": 2,
          "price": 15000,
          "subtotal": 30000,
          "notes": "Tanpa gula"
        },
        {
          "product": 2,
          "product_name": "Nasi Goreng",
          "quantity": 1,
          "price": 25000,
          "subtotal": 25000,
          "notes": "ga pedes"
        }
      ]
    }
    """
    serializer = TransactionSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        transaction = serializer.save()
        
        return Response({
            'message': 'Transaksi berhasil dibuat',
            'data': TransactionSerializer(transaction).data
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        'message': 'Gagal membuat transaksi',
        'errors': serializer.errors
    }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET', 'PATCH', 'DELETE'])
def get_update_delete_transaction(request, transaction_id):
    """
    Mendapatkan, mengupdate, atau menghapus transaksi berdasarkan ID
    GET /api/transaction/<transaction_id>/
    PATCH /api/transaction/<transaction_id>/
    DELETE /api/transaction/<transaction_id>/
    """
    if request.method == 'GET':
      try:
        transaction = Transaction.objects.get(id=transaction_id)
      except Transaction.DoesNotExist:
        return Response({ 'message': "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)

      serializer = TransactionSerializer(transaction)
      return Response({'message:': 'Success', 'data': serializer.data}, status=status.HTTP_200_OK)
    elif request.method == 'PATCH':
      try:
        transaction = Transaction.objects.get(id=transaction_id)
      except Transaction.DoesNotExist:
        return Response({ 'message': "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)

      serializer = TransactionSerializer(transaction, data=request.data, partial=True)
      serializer.is_valid(raise_exception=True)
      serializer.save()

      return Response({
        'message': 'Transaksi berhasil diupdate',
        'data': serializer.data
      }, status=status.HTTP_200_OK)

    elif request.method == 'DELETE':    
      try:
        transaction = Transaction.objects.get(id=transaction_id)
      except Transaction.DoesNotExist:
        return Response({ 'message': "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)

      transaction.delete()

      return Response({
        'message': 'Transaksi berhasil dihapus',
      }, status=status.HTTP_200_OK)
    
@api_view(['GET'])
def list_transactions(request):
    """
    Mendapatkan daftar transaksi dengan filter tanggal dan pagination
    GET /api/transaction/?start_date=2025-12-01&end_date=2025-12-07&page=2&page_size=10
    """
    transactions = Transaction.objects.all()

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

    # slicing di QuerySet LIMIT + OFFSET
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

    ##################### MANUAL SQL QUERY ####################################################################

    # start_date = request.GET.get('start_date')
    # end_date = request.GET.get('end_date')
    # page = int(request.GET.get('page', 1))
    # page_size = int(request.GET.get('page_size', 10))
    # offset = (page - 1) * page_size

    # where_clauses = []
    # params = []

    # if start_date and end_date:
    #     # Filter date range
    #     where_clauses.append("created_at BETWEEN %s AND %s")
    #     params.extend([f'{start_date} 00:00:00', f'{end_date} 23:59:59'])

    # where_sql = " AND ".join(where_clauses)
    # if where_sql:
    #     where_sql = "WHERE " + where_sql

    # # Total count
    # count_query = f"SELECT COUNT(*) FROM transaction {where_sql}"
    # with connection.cursor() as cursor:
    #     cursor.execute(count_query, params)
    #     total_items = cursor.fetchone()[0]

    # # Ambil transaksi page ini
    # data_query = f"""
    #     SELECT * FROM transaction
    #     {where_sql}
    #     ORDER BY created_at DESC
    #     LIMIT %s OFFSET %s
    # """
    # with connection.cursor() as cursor:
    #     cursor.execute(data_query, params + [page_size, offset])
    #     columns = [col[0] for col in cursor.description]
    #     transactions = [dict(zip(columns, row)) for row in cursor.fetchall()]

    # # Ambil transaction_item untuk setiap transaksi
    # transaction_ids = [t['id'] for t in transactions]
    # if transaction_ids:
    #     format_ids = ','.join(['%s'] * len(transaction_ids))
    #     item_query = f"""
    #         SELECT * FROM transaction_item
    #         WHERE transaction_id IN ({format_ids})
    #     """
    #     with connection.cursor() as cursor:
    #         cursor.execute(item_query, transaction_ids)
    #         item_columns = [col[0] for col in cursor.description]
    #         items = [dict(zip(item_columns, row)) for row in cursor.fetchall()]

    #     # Group items per transaction
    #     items_by_transaction = {}
    #     for item in items:
    #         tid = item['transaction_id']
    #         if tid not in items_by_transaction:
    #             items_by_transaction[tid] = []
    #         items_by_transaction[tid].append(item)

    #     # Attach items ke transaksi
    #     for t in transactions:
    #         t['items'] = items_by_transaction.get(t['id'], [])
    # else:
    #     for t in transactions:
    #         t['items'] = []

    # return Response({
    #     'message': 'Success',
    #     'total_items': total_items,
    #     'page': page,
    #     'page_size': page_size,
    #     'data': transactions
    # })