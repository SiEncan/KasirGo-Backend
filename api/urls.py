from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import get_all_users, get_update_delete_user, create_user, change_password, create_category, \
                   get_all_categories, get_update_delete_category, create_product, get_all_products, \
                   get_update_delete_product, create_transaction, get_update_delete_transaction, \
                   list_transactions, LogoutView

urlpatterns = [

  # User endpoints
  path('users/', get_all_users, name='get_all_users'),
  path('user/<uuid:user_id>/', get_update_delete_user, name='get_update_delete_user'),
  path('user/<uuid:user_id>/change-password/', change_password, name='change_password'),
  path('users/create/', create_user, name='create_user'),

  # Category endpoints
  path('category/', get_all_categories, name='get_all_categories'),
  path('category/<int:category_id>/', get_update_delete_category, name='get_update_delete_category'),
  path('category/create/', create_category, name='create_category'),

  # Product endpoints
  path('product/', get_all_products, name='get_all_products'),
  path('product/<int:product_id>/', get_update_delete_product, name='get_update_delete_product'),
  path('product/create/', create_product, name='create_product'),

  # Transaction endpoints
  path('transaction/', list_transactions, name='list_transactions'),
  path('transaction/<int:transaction_id>/', get_update_delete_transaction, name='get_update_delete_transaction'),
  path('transaction/create/', create_transaction, name='create_transaction'),

  # JWT endpoints
  path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
  path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
  path('auth/logout/', LogoutView.as_view(), name='logout'),
]