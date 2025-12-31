from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from django.db import connection, transaction
from django.db.models import Q
from api.models import Product
from api.serializer import CategorySerializer, ProductSerializer

from api.utils_transaction import cleanup_expired_transactions

@api_view(['GET'])
def get_all_categories(request):
  """
  Mendapatkan semua kategori produk
  GET /api/category/
  """

  with connection.cursor() as cursor:
    if request.user.cafe:
      cursor.execute("SELECT id, name, description, created_at, updated_at FROM category WHERE cafe_id = %s ORDER BY created_at DESC", [request.user.cafe.id])
    else:
      cursor.execute("SELECT id, name, description, created_at, updated_at FROM category WHERE cafe_id IS NULL ORDER BY created_at DESC")
        
    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]
    result = [dict(zip(columns, row)) for row in rows]

  return Response({'message:': 'Success', 'data': result}, status=status.HTTP_200_OK)

@api_view(['POST'])
def create_category(request):
  """
  Membuat kategori produk baru
  POST /api/category/create/
  """

  if request.user.role != 'owner' and not request.user.is_superuser:
    return Response({
      'message': 'You do not have permission'
    }, status=status.HTTP_403_FORBIDDEN)

  serializer = CategorySerializer(data=request.data)
  serializer.is_valid(raise_exception=True)
  data = serializer.validated_data

  name = data.get('name')
  description = data.get('description')

  cafe_id = request.user.cafe.id if request.user.cafe else None

  with connection.cursor() as cursor:
    cursor.execute("""
      INSERT INTO category (name, description, cafe_id, created_at, updated_at)
      VALUES (%s, %s, %s, NOW(), NOW())
      RETURNING name, description
    """, [name, description, cafe_id])

    columns = [col[0] for col in cursor.description]
    category_data = dict(zip(columns, cursor.fetchone()))
  
  return Response({
    'message': 'Category has been created',
    'data': category_data
  }, status=status.HTTP_201_CREATED)

@api_view(['GET', 'PATCH', 'DELETE'])
def get_update_delete_category(request, category_id):
  """
  Mendapatkan, mengupdate, atau menghapus kategori produk berdasarkan ID
  """
  if not request.user.cafe:
    return Response({'message': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

  # For reading:
  if request.method == 'GET':
    with connection.cursor() as cursor:
      cursor.execute("SELECT name, description, created_at, updated_at FROM category WHERE id = %s AND cafe_id = %s", [category_id, request.user.cafe.id])
      row = cursor.fetchone()
      if not row:
        return Response({'message': 'Category not found'}, status=status.HTTP_404_NOT_FOUND)
      
      columns = [col[0] for col in cursor.description]
      category_data = dict(zip(columns, row))

    return Response({'message:': 'Success', 'data': category_data}, status=status.HTTP_200_OK)

  elif request.method == 'PATCH':

    if request.user.role != 'owner' and not request.user.is_superuser:
      return Response({
        'message': 'You do not have permission'
      }, status=status.HTTP_403_FORBIDDEN)
    
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
      cursor.execute("SELECT id FROM category WHERE id = %s AND cafe_id = %s", [category_id, request.user.cafe.id])
      if not cursor.fetchone():
        return Response({'message': 'Category not found'}, status=status.HTTP_404_NOT_FOUND)
      
      if len(params) == 0:
        return Response({
          'message': 'No data to update'
        }, status=status.HTTP_400_BAD_REQUEST)
      
      params.append(category_id)
      params.append(request.user.cafe.id)

      sql = f"""
              UPDATE category 
              SET {', '.join(updates)}
              WHERE id = %s AND cafe_id = %s
              RETURNING name, description, created_at, updated_at
            """
      cursor.execute(sql, params)

      columns = [col[0] for col in cursor.description]
      category_data = dict(zip(columns, cursor.fetchone()))

    return Response({
      'message': 'Category has been updated',
      'data': category_data
    }, status=status.HTTP_200_OK)

  elif request.method == 'DELETE':

    if request.user.role != 'owner' and not request.user.is_superuser:
      return Response({
        'message': 'You do not have permission'
      }, status=status.HTTP_403_FORBIDDEN)
    
    with connection.cursor() as cursor:
      cursor.execute("SELECT id FROM category WHERE id = %s AND cafe_id = %s", [category_id, request.user.cafe.id])
      if not cursor.fetchone():
        return Response({'message': 'Category not found'}, status=status.HTTP_404_NOT_FOUND)
      
      cursor.execute("UPDATE product SET category_id = NULL WHERE category_id = %s AND cafe_id = %s", [category_id, request.user.cafe.id])
      
      cursor.execute("DELETE FROM category WHERE id = %s AND cafe_id = %s", [category_id, request.user.cafe.id])
    
    return Response({
      'message': 'Category has been deleted'
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
@transaction.atomic
def create_product(request):
  """
  Membuat produk baru
  POST /api/product/create/
  """
  if request.user.role != 'owner' and not request.user.is_superuser:
    return Response({
      'message': 'You do not have permission'
    }, status=status.HTTP_403_FORBIDDEN)
  
  serializer = ProductSerializer(data=request.data)
  serializer.is_valid(raise_exception=True)
  product = serializer.save(cafe=request.user.cafe) # Inject Tenant

  return Response({
    'message': 'Product has been created',
    'data': ProductSerializer(product).data
  }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
def search_products(request):
  """
  Mencari produk berdasarkan berbagai kriteria
  """

  name = request.GET.get('name', '')
  category_id = request.GET.get('category', '')
  min_price = request.GET.get('min_price', '')
  max_price = request.GET.get('max_price', '')
  is_available = request.GET.get('available', '')
  
  # Base Filter: Tenant Isolation
  products = Product.objects.filter(cafe=request.user.cafe)
  
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
  # Clean up expired transactions first to ensure stock is accurate
  if request.user.cafe:
    cleanup_expired_transactions(request.user.cafe)

  products = Product.objects.filter(cafe=request.user.cafe)
  serializer = ProductSerializer(products, many=True)

  return Response({'message:': 'Success', 'data': serializer.data}, status=status.HTTP_200_OK)


@api_view(['GET', 'PATCH', 'DELETE'])
def get_update_delete_product(request, product_id):
  """
  Mendapatkan, mengupdate, atau menghapus produk berdasarkan ID
  """

  if request.method == 'GET':
    try:
      product = Product.objects.get(id=product_id, cafe=request.user.cafe)
    except Product.DoesNotExist:
      return Response({ 'message': "Product not found"}, status= status.HTTP_404_NOT_FOUND)

    result = ProductSerializer(product).data

    return Response({'message:': 'Success', 'data': result}, status=status.HTTP_200_OK)
  
  elif request.method == 'PATCH':
    if request.user.role != 'owner' and not request.user.is_superuser:
      return Response({
        'message': 'You do not have permission'
      }, status=status.HTTP_403_FORBIDDEN)
    try:
      product = Product.objects.get(id=product_id, cafe=request.user.cafe)
    except Product.DoesNotExist:
      return Response({ 'message': "Product not found"}, status= status.HTTP_404_NOT_FOUND)

    serializer = ProductSerializer(product, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()

    return Response({
      'message': 'Product has been updated',
      'data': serializer.data
    }, status=status.HTTP_200_OK)
  
  elif request.method == 'DELETE':
    if request.user.role != 'owner' and not request.user.is_superuser:
      return Response({
        'message': 'You do not have permission'
      }, status=status.HTTP_403_FORBIDDEN)
    try:
      product = Product.objects.get(id=product_id, cafe=request.user.cafe)
    except Product.DoesNotExist:
      return Response({ 'message': "Product not found"}, status= status.HTTP_404_NOT_FOUND)

    product.delete()

    return Response({
      'message': 'Product has been deleted'
    }, status=status.HTTP_200_OK)
