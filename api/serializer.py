from rest_framework import serializers
from .models import Category, Product, Transaction, TransactionItem, User, Payment
from decimal import Decimal

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'username', 'email', 'role', 'phone']

class CreateUserSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    username = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField(default="cashier")
    phone = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField()

class CategorySerializer(serializers.ModelSerializer):
  class Meta:
        model = Category
        fields = '__all__'

class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    image = serializers.ImageField(required=False, allow_null=True)
    
    class Meta:
        model = Product
        fields = '__all__'

class TransactionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionItem
        fields = ['product', 'product_name', 'quantity', 'price', 'subtotal', 'notes']

class TransactionSerializer(serializers.ModelSerializer):
    items = TransactionItemSerializer(many=True)
    cashier_name = serializers.CharField(source='cashier.username', read_only=True)
    customer_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    order_type = serializers.ChoiceField(choices=Transaction.ORDER_TYPE_CHOICES, default='dine_in')
    
    class Meta:
        model = Transaction
        fields = '__all__'
        read_only_fields = ['transaction_number', 'cashier']
    
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        cashier = self.context['request'].user

        transaction_subtotal = 0
        transaction = Transaction.objects.create(cashier=cashier, **validated_data)

        for item_data in items_data:
            product = Product.objects.get(id=item_data['product'].id)
            quantity = item_data.get('quantity', 1)
            price = product.price
            subtotal = price * quantity

            # Update subtotal
            transaction_subtotal += subtotal

            # Buat TransactionItem
            TransactionItem.objects.create(
                transaction=transaction,
                product=product,
                product_name=product.name,
                quantity=quantity,
                price=price,
                subtotal=subtotal,
                notes=item_data.get('notes', '')
            )

            # Update stock
            product.stock -= quantity
            product.save()

        # Hitung tax (misal 11% PPN) dan total
        tax_percentage = validated_data.get('tax_percentage', Decimal('0.11'))
        tax = transaction_subtotal * tax_percentage
        total = transaction_subtotal + tax - validated_data.get('discount', Decimal('0.00'))
        change_amount = validated_data['paid_amount'] - total
        change_amount = change_amount if change_amount > 0 else 0

        # Update transaction dengan subtotal, tax, total, change
        transaction.subtotal = transaction_subtotal
        transaction.tax = tax
        transaction.total = total
        transaction.change_amount = change_amount
        transaction.save()

        return transaction

    
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        
        # Update field biasa
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if items_data is not None:
            # Kembalikan stock item lama
            for item in instance.items.all():
                product = item.product
                product.stock += item.quantity
                product.save()
            instance.items.all().delete()
            
            # Tambahkan item baru & kurangi stock
            transaction_subtotal = 0
            for item_data in items_data:
                product = Product.objects.get(id=item_data['product'].id)
                quantity = item_data.get('quantity', 1)
                subtotal = product.price * quantity
                transaction_subtotal += subtotal

                TransactionItem.objects.create(
                    transaction=instance,
                    product=product,
                    product_name=product.name,
                    quantity=quantity,
                    price=product.price,
                    subtotal=subtotal,
                    notes=item_data.get('notes', '')
                )

                product.stock -= quantity
                product.save()
            
            instance.subtotal = transaction_subtotal
            instance.total = transaction_subtotal + instance.tax - instance.discount
            instance.change_amount = max(0, instance.paid_amount - instance.total)
        
        instance.save()
        return instance


class PaymentSerializer(serializers.ModelSerializer):
    transaction_number = serializers.CharField(source='transaction.transaction_number', read_only=True)
    
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ['merchant_order_id', 'reference', 'payment_url', 'va_number', 
                          'qr_string', 'status', 'status_code', 'status_message', 
                          'callback_data', 'expired_at', 'paid_at']


class CreatePaymentSerializer(serializers.Serializer):
    transaction_id = serializers.IntegerField()
    payment_method = serializers.CharField(default='SP')  # SP = QRIS