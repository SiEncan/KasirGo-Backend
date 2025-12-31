from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from django.db import connection, transaction
from django.contrib.auth.hashers import make_password, check_password
import uuid

# Import models & serializers from parent 'api' package
from api.serializer import CreateUserSerializer
from api.models import User

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
        return Response({"error": "Cannot logout token of another user"}, status=403)

      token_obj.blacklist()  # invalidate token
      return Response({"message": "Logout successful"}, status=status.HTTP_205_RESET_CONTENT)
    except (TokenError, InvalidToken) as e:
      return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)
      
@api_view(['GET'])
def get_all_users(request):
  """
  Mendapatkan semua user (Admin Only)
  GET /api/users/
  """
  if request.user.role != 'owner':
    return Response({
      'message': 'Anda tidak memiliki izin untuk mengakses data ini'
    }, status=status.HTTP_403_FORBIDDEN)

  # Filter by Cafe for Multi-Tenancy (Future Phase 2 scope, but scoped user list is good)
  # For now, admin sees all users in their cafe
  with connection.cursor() as cursor:
    if request.user.cafe:
      cursor.execute("SELECT id, username, email, first_name, last_name, role, phone, is_active, date_joined, last_login FROM users \
                    WHERE cafe_id = %s ORDER BY date_joined DESC", [request.user.cafe.id])
    elif request.user.is_superuser:
      # Super admin fallback
      cursor.execute("SELECT id, username, email, first_name, last_name, role, phone, is_active, date_joined, last_login, cafe_id FROM users \
                    ORDER BY date_joined DESC")
    else:
      return Response({'message': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

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
  """
  serializer = CreateUserSerializer(data=request.data)
  serializer.is_valid(raise_exception=True)
  data = serializer.validated_data

  first_name = data.get('first_name')
  last_name = data.get('last_name')
  username = data.get('username')
  email = data.get('email')
  role = data.get('role', 'staff')
  phone = data.get('phone', '')
  password = data.get('password')
  new_id = str(uuid.uuid4())

  with connection.cursor() as cursor: # auto close cursor
    # Cek username sudah ada atau belum
    cursor.execute('SELECT id FROM users WHERE username = %s', [username])
    if cursor.fetchone():
      return Response({
        'message': 'Username is already in use'
      }, status=status.HTTP_400_BAD_REQUEST)
    
    # Cek email sudah ada atau belum
    cursor.execute('SELECT id FROM users WHERE email = %s', [email])
    if cursor.fetchone():
      return Response({
        'message': 'Email is already in use'
      }, status=status.HTTP_400_BAD_REQUEST)
    
    # hash password
    hashed_password = make_password(password)

    # Set is_staff based on role
    # Logic for Authenticated Admin (Add Staff) vs Anonymous (Signup Owner)
    cafe_id = None
    
    if request.user and request.user.is_authenticated:
      # Add Staff Mode: Inherit Cafe
      if request.user.cafe:
        cafe_id = request.user.cafe.id
    else:
      # Signup Mode (New Owner)
      cafe_name = data.get('cafe_name')
      if not cafe_name:
        return Response({'message': 'Cafe name is required for registration'}, status=status.HTTP_400_BAD_REQUEST)
      
      # Create Cafe
      cursor.execute("INSERT INTO cafes (name, created_at, updated_at) VALUES (%s, NOW(), NOW()) RETURNING id", [cafe_name])
      cafe_row = cursor.fetchone()
      cafe_id = cafe_row[0]
      
      # Force Role to Owner for new signups
      role = 'owner'

    # Set is_staff based on role (Owner gets access to Django Admin if needed)
    is_staff = True if role == 'owner' else False
    
    cursor.execute("INSERT INTO users (id, first_name, last_name, username, email, role, phone, " \
                  "is_active, is_superuser, is_staff, password, date_joined, updated_at, created_at, last_login, cafe_id) " \
                  "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW(), NULL, %s) " \
                  "RETURNING first_name, last_name, username, email, role, phone", 
                  [new_id,first_name, last_name, username, email, role, phone, True, False, is_staff, hashed_password, cafe_id])
    
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
  """

  if str(user_id) != str(request.user.id) and request.user.role != 'owner':
    return Response({
      'message': 'You do not have permission to access this data'
    }, status=status.HTTP_403_FORBIDDEN)

  old_password = request.data.get('old_password')
  new_password = request.data.get('new_password')
  
  # Validasi
  if not old_password or not new_password:
    return Response({
      'message': 'Old password and new password are required'
    }, status=status.HTTP_400_BAD_REQUEST)
  
  if len(new_password) < 8:
    return Response({
      'message': 'Password must be at least 8 characters long'
    }, status=status.HTTP_400_BAD_REQUEST)
  
  with connection.cursor() as cursor:
    # Ambil password lama dari database
    cursor.execute(
      'SELECT password FROM users WHERE id = %s', 
      [user_id]
    )
    row = cursor.fetchone()
    if not row:
        return Response({'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    db_old_password = row[0] 
    
    # Verifikasi password lama
    if not check_password(old_password, db_old_password):
      return Response({
        'message': 'Old Password does not match'
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
  """
  if str(user_id) != str(request.user.id) and request.user.role != 'owner':
    return Response({
      'message': 'You do not have permission to access this data'
    }, status=status.HTTP_403_FORBIDDEN)
  
  if request.method == 'GET':

    with connection.cursor() as cursor:
      # Secure: Filter by ID AND Cafe (unless global admin logic changes)
      if request.user.cafe:
        cursor.execute("SELECT username, email, first_name, last_name, role, phone, is_active, date_joined, last_login, cafe_id \
          FROM users WHERE id = %s AND cafe_id = %s", (user_id, request.user.cafe.id))
      elif request.user.is_superuser:
        cursor.execute("SELECT username, email, first_name, last_name, role, phone, is_active, date_joined, last_login, cafe_id \
          FROM users WHERE id = %s", (user_id,))
      else:
        return Response({'message': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

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
        'message': 'No data to update'
      }, status=status.HTTP_400_BAD_REQUEST)
    
    params.append(user_id)

    sql = f"""
          UPDATE users 
          SET {', '.join(updates)}
          WHERE id = %s
          RETURNING first_name, last_name, username, email, role, phone
        """

    with connection.cursor() as cursor:
      if request.user.cafe:
        cursor.execute("SELECT id FROM users WHERE id = %s AND cafe_id = %s", [user_id, request.user.cafe.id])
      elif request.user.is_superuser:
        cursor.execute("SELECT id FROM users WHERE id = %s", [user_id])
      else:
        return Response({'message': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
          
      if not cursor.fetchone():
        return Response({
          'message': 'User not found'
        }, status = status.HTTP_404_NOT_FOUND)
      
      cursor.execute(sql, params)

      columns = [col[0] for col in cursor.description]
      user_data = dict(zip(columns, cursor.fetchone()))

    return Response({
        'message': 'User has been updated',
        'data': user_data
    }, status=status.HTTP_200_OK)
  
  elif request.method == 'DELETE':
    with connection.cursor() as cursor:
      if request.user.cafe:
        cursor.execute("SELECT id FROM users WHERE id = %s AND cafe_id = %s", [user_id, request.user.cafe.id])
      elif request.user.is_superuser:
        cursor.execute("SELECT id FROM users WHERE id = %s", [user_id])
      else:
        return Response({'message': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)

      if not cursor.fetchone():
        return Response({
          'message': 'User not found'
        }, status = status.HTTP_404_NOT_FOUND)
      
      cursor.execute("DELETE FROM users WHERE id = %s", [user_id])
    
    return Response({
      'message': 'User has been deleted'
    }, status=status.HTTP_200_OK)
