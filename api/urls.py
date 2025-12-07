from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import get_all_users, get_user_by_id, create_user, change_password, create_category, \
                   get_all_categories, get_category_by_id, create_product, get_all_products, \
                   get_product_by_id, create_transaction, get_all_transactions, get_transaction_by_id

urlpatterns = [
  path('users/', get_all_users, name='get_all_users'),
  path('user/<uuid:user_id>/', get_user_by_id, name='get_user_by_id'),
  path('user/<uuid:user_id>/change-password/', change_password, name='change_password'),
  path('users/create/', create_user, name='create_user'),
  path('category/', get_all_categories, name='get_all_categories'),
  path('category/<int:category_id>/', get_category_by_id, name='get_category_by_id'),
  path('category/create/', create_category, name='create_category'),
  path('product/', get_all_products, name='get_all_products'),
  path('product/<int:product_id>/', get_product_by_id, name='get_product_by_id'),
  path('product/create/', create_product, name='create_product'),
  path('transaction/', get_all_transactions, name='get_all_transactions'),
  path('transaction/<int:transaction_id>/', get_transaction_by_id, name='get_transaction_by_id'),
  path('transaction/create/', create_transaction, name='create_transaction'),

  # JWT endpoints
  path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
  path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh')
]