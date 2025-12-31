from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Migrates old roles (admin/manager -> owner, cashier -> staff)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting role migration...'))
        
        with connection.cursor() as cursor:
            # 1. Update Managers and Admins (Tenant Scope) to 'owner'
            # Update legacy 'manager' AND 'admin' roles to 'owner' IF they are associated with a cafe
            cursor.execute("UPDATE users SET role = 'owner' WHERE role IN ('manager', 'admin') AND cafe_id IS NOT NULL")
            owner_count = cursor.rowcount
            
            # 2. Update Cashiers to 'staff'
            cursor.execute("UPDATE users SET role = 'staff' WHERE role = 'cashier'")
            staff_count = cursor.rowcount
            
        self.stdout.write(self.style.SUCCESS(f'Successfully updated {owner_count} Owners and {staff_count} Staff.'))
