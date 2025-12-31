from django.db import migrations

def assign_default_cafe(apps, schema_editor):
    Cafe = apps.get_model('api', 'Cafe')
    User = apps.get_model('api', 'User')
    Category = apps.get_model('api', 'Category')
    Product = apps.get_model('api', 'Product')
    Transaction = apps.get_model('api', 'Transaction')

    # 1. Create Default Cafe if none exists
    default_cafe, created = Cafe.objects.get_or_create(
        name="KasirGo HQ",
        defaults={
            'address': 'Default Address',
            'phone': '0000000000'
        }
    )

    if created:
        print(f"\nCreated Default Cafe: {default_cafe.name} (ID: {default_cafe.id})")
    else:
        print(f"\nUsing Existing Default Cafe: {default_cafe.name}")

    # 2. Assign Orphans to Default Cafe
    # Users
    users_updated = User.objects.filter(cafe__isnull=True).update(cafe=default_cafe)
    print(f"Updated {users_updated} Users")

    # Categories
    cats_updated = Category.objects.filter(cafe__isnull=True).update(cafe=default_cafe)
    print(f"Updated {cats_updated} Categories")

    # Products
    prods_updated = Product.objects.filter(cafe__isnull=True).update(cafe=default_cafe)
    print(f"Updated {prods_updated} Products")

    # Transactions
    trx_updated = Transaction.objects.filter(cafe__isnull=True).update(cafe=default_cafe)
    print(f"Updated {trx_updated} Transactions")

class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_cafe_alter_payment_merchant_order_id_and_more'),
    ]

    operations = [
        migrations.RunPython(assign_default_cafe),
    ]
