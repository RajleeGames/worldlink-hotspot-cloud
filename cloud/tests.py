from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Company,Membership
from networks.models import Location,Router,WifiPlan
from vouchers.models import VoucherBatch,Voucher,ManualSale
from decimal import Decimal

class TenantSecurityTests(TestCase):
    def setUp(self):
        self.user1=get_user_model().objects.create_user(username='one@example.com',email='one@example.com',password='strong-test-password-443')
        self.user2=get_user_model().objects.create_user(username='two@example.com',email='two@example.com',password='strong-test-password-998')
        self.a=Company.objects.create(name='A Company')
        self.b=Company.objects.create(name='B Company')
        Membership.objects.create(company=self.a,user=self.user1,role='OWNER')
        Membership.objects.create(company=self.b,user=self.user2,role='OWNER')
        self.loc_a=Location.objects.create(company=self.a,name='A site')
        self.loc_b=Location.objects.create(company=self.b,name='B site')
        self.router_b=Router.objects.create(company=self.b,location=self.loc_b,name='PRIVATE B ROUTER')
        self.plan_a=WifiPlan.objects.create(company=self.a,name='A package',duration_minutes=60,price=Decimal('500.00'))
        self.plan_b=WifiPlan.objects.create(company=self.b,name='B private',duration_minutes=180,price=Decimal('1000.00'))

    def test_login_required(self):
        response=self.client.get(reverse('networks:routers'))
        self.assertEqual(response.status_code,302)
        self.assertIn('/login/',response['Location'])

    def test_business_isolation_on_lists_and_update(self):
        self.client.force_login(self.user1)
        response=self.client.get(reverse('networks:routers'))
        self.assertNotContains(response,'PRIVATE B ROUTER')
        response=self.client.post(reverse('networks:router_edit',args=[self.router_b.pk]),{'name':'attack','location':self.loc_a.pk,'family':'MIKROTIK'})
        self.assertEqual(response.status_code,404)
        self.router_b.refresh_from_db()
        self.assertEqual(self.router_b.name,'PRIVATE B ROUTER')

    def test_cannot_assign_other_business_plan_or_location(self):
        self.client.force_login(self.user1)
        response=self.client.post(reverse('networks:router_new'),{'name':'bad','location':self.loc_b.pk,'family':'MIKROTIK'})
        self.assertEqual(Router.objects.filter(company=self.a).count(),0)
        response=self.client.post(reverse('vouchers:create'),{'plan':self.plan_b.pk,'quantity':2})
        self.assertEqual(Voucher.objects.filter(company=self.a).count(),0)

    def test_voucher_generation_and_sale(self):
        self.client.force_login(self.user1)
        response=self.client.post(reverse('vouchers:create'),{'plan':self.plan_a.pk,'quantity':3,'label':'Desk'},follow=True)
        self.assertEqual(Voucher.objects.filter(company=self.a).count(),3)
        voucher=Voucher.objects.filter(company=self.a).first()
        self.client.post(reverse('vouchers:sell',args=[voucher.pk]),{'method':'CASH'})
        self.client.post(reverse('vouchers:sell',args=[voucher.pk]),{'method':'CASH'})
        self.assertEqual(ManualSale.objects.filter(company=self.a).count(),1)
        self.assertEqual(ManualSale.objects.get(company=self.a).amount,Decimal('500.00'))

    def test_cross_company_sale_forbidden(self):
        batch=VoucherBatch.objects.create(company=self.b,plan=self.plan_b,quantity=1,created_by=self.user2)
        voucher=Voucher.objects.create(company=self.b,batch=batch,code='WHC-TESTAAAAA')
        self.client.force_login(self.user1)
        self.assertEqual(self.client.post(reverse('vouchers:sell',args=[voucher.pk]),{'method':'CASH'}).status_code,404)
        self.assertFalse(ManualSale.objects.exists())

    def test_cashier_cannot_edit_packages(self):
        Membership.objects.filter(user=self.user1).update(role='CASHIER')
        self.client.force_login(self.user1)
        response=self.client.post(reverse('networks:plan_new'),{'name':'wrong','duration_minutes':60,'price':500,'download_kbps':1000,'upload_kbps':500,'device_limit':1})
        self.assertEqual(response.status_code,403)

    def test_language_and_safe_redirect(self):
        response=self.client.post(reverse('language_change'),{'language':'sw','next':'https://evil.example'})
        self.assertEqual(response['Location'],'/')
        self.assertEqual(self.client.session['ui_lang'],'sw')

class BrandingTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='brand@example.com', password='strong-brand-password-123')
        self.company = Company.objects.create(name='Branded Business')
        Membership.objects.create(company=self.company, user=self.owner, role='OWNER')

    def test_company_logo_form_uses_multipart_and_favicon_fallback(self):
        self.client.force_login(self.owner)
        page = self.client.get(reverse('tenants:settings'))
        self.assertContains(page, 'enctype="multipart/form-data"')
        self.assertContains(page, 'name="logo"')
        self.assertContains(page, 'favicon.svg')

    def test_platform_brand_logo_rendered_in_login(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import PlatformBranding
        from PIL import Image
        from io import BytesIO
        out = BytesIO()
        Image.new('RGB', (16, 16), (23, 112, 105)).save(out, format='PNG')
        from django.test import override_settings
        import tempfile
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            logo = SimpleUploadedFile('logo.png', out.getvalue(), content_type='image/png')
            brand = PlatformBranding.objects.create(logo=logo)
            response = self.client.get(reverse('login'))
            self.assertContains(response, brand.logo.url)
            self.assertContains(response, 'rel="icon"')

    def test_owner_can_upload_company_logo(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        from io import BytesIO
        from PIL import Image
        import tempfile
        out = BytesIO()
        Image.new('RGB', (32, 32), (14, 125, 115)).save(out, format='PNG')
        self.client.force_login(self.owner)
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            response = self.client.post(reverse('tenants:settings'), {
                'name': self.company.name, 'email': '', 'phone': '', 'city': '',
                'logo': SimpleUploadedFile('business.png', out.getvalue(), content_type='image/png'),
            })
            self.assertEqual(response.status_code, 302)
            self.company.refresh_from_db()
            self.assertTrue(self.company.logo.name.startswith('branding/businesses/'))


class WorkspaceCrudTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(username='owner-c@example.com', password='valid-test-pass-123')
        self.other = get_user_model().objects.create_user(username='other-c@example.com', password='valid-test-pass-123')
        self.a = Company.objects.create(name='Operator A')
        self.b = Company.objects.create(name='Operator B')
        Membership.objects.create(company=self.a,user=self.owner,role='OWNER')
        Membership.objects.create(company=self.b,user=self.other,role='OWNER')
        self.loc = Location.objects.create(company=self.a,name='Main site')
        self.other_expense = __import__('cloud.models', fromlist=['Expense']).Expense.objects.create(company=self.b,date='2026-11-02',description='Other company secret',amount=200,recorded_by=self.other)
        self.client.force_login(self.owner)

    def test_breadcrumbs_include_current_location(self):
        page=self.client.get(reverse('networks:locations'))
        self.assertContains(page,'aria-label="Breadcrumb"')
        self.assertContains(page,'Network')
        self.assertContains(page,'Locations')

    def test_location_delete_get_denied_and_cross_company_hidden(self):
        delete_url=reverse('networks:location_delete',args=[self.loc.pk])
        self.assertEqual(self.client.get(delete_url).status_code,405)
        response=self.client.post(delete_url)
        self.assertEqual(response.status_code,302)
        self.assertFalse(Location.objects.filter(pk=self.loc.pk).exists())

    def test_delete_location_with_router_shows_error(self):
        Router.objects.create(company=self.a,location=self.loc,name='Router 1')
        self.client.post(reverse('networks:location_delete',args=[self.loc.pk]))
        self.assertTrue(Location.objects.filter(pk=self.loc.pk).exists())

    def test_expense_crud_and_tenant_isolation(self):
        from cloud.models import Expense
        self.assertNotContains(self.client.get(reverse('cloud:expenses')),'Other company secret')
        self.assertEqual(self.client.post(reverse('cloud:expense_delete',args=[self.other_expense.pk])).status_code,404)
        response=self.client.post(reverse('cloud:expense_new'),{'date':'2026-11-02','category':'INTERNET','description':'Monthly uplink','amount':'25000'})
        self.assertEqual(response.status_code,302)
        expense=Expense.objects.get(company=self.a)
        self.assertEqual(expense.recorded_by,self.owner)
        self.client.post(reverse('cloud:expense_edit',args=[expense.pk]),{'date':'2026-11-02','category':'POWER','description':'Electricity','amount':'15000'})
        expense.refresh_from_db();self.assertEqual(expense.description,'Electricity')
        self.client.post(reverse('cloud:expense_delete',args=[expense.pk]))
        self.assertFalse(Expense.objects.filter(pk=expense.pk).exists())

    def test_cashier_cannot_delete_routers_or_expenses(self):
        Membership.objects.filter(company=self.a,user=self.owner).update(role='CASHIER')
        router=Router.objects.create(company=self.a,location=self.loc,name='Safe router')
        self.assertEqual(self.client.post(reverse('networks:router_delete',args=[router.pk])).status_code,403)
        self.assertEqual(self.client.post(reverse('cloud:expense_new'),{}).status_code,403)
        self.assertTrue(Router.objects.filter(pk=router.pk).exists())

    def test_voucher_batch_history_protected(self):
        plan=WifiPlan.objects.create(company=self.a,name='One Hour',duration_minutes=60,price=500)
        batch=VoucherBatch.objects.create(company=self.a,plan=plan,quantity=1,created_by=self.owner)
        Voucher.objects.create(company=self.a,batch=batch,code='WHC-MORETEST12',status='SOLD')
        self.client.post(reverse('vouchers:batch_delete',args=[batch.pk]))
        self.assertTrue(VoucherBatch.objects.filter(pk=batch.pk).exists())

    def test_duplicate_location_name_is_shown_as_form_error(self):
        response=self.client.post(reverse('networks:location_new'),{'name':'MAIN SITE','address':''})
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'already exists')
