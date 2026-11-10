from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from tenants.models import Company, Membership
from .models import PlatformAudit

User=get_user_model()

class PlatformConsoleTests(TestCase):
    def setUp(self):
        self.business=Company.objects.create(name='Moshi Demo',status='TRIAL')
        self.owner=User.objects.create_user(username='tenant@example.com',password='VerySecurePassword123!')
        Membership.objects.create(company=self.business,user=self.owner,role='OWNER')
        self.staff=User.objects.create_user(username='staff@example.com',password='VerySecurePassword123!',is_staff=True)
        self.platform=User.objects.create_superuser(username='platform@example.com',password='VerySecurePassword123!')

    def test_business_owner_denied_console(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('controlcenter:overview')).status_code,403)
        self.assertEqual(self.client.get(reverse('controlcenter:users')).status_code,403)
        self.assertEqual(self.client.post(reverse('controlcenter:business_update',args=[self.business.pk]),{'status':'SUSPENDED'}).status_code,403)

    def test_staff_without_permission_denied(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('controlcenter:overview')).status_code,403)
        self.staff.user_permissions.add(Permission.objects.get(codename='view_platform_console'))
        self.staff=User.objects.get(pk=self.staff.pk)
        self.assertEqual(self.client.get(reverse('controlcenter:overview')).status_code,200)
        self.assertEqual(self.client.post(reverse('controlcenter:business_update',args=[self.business.pk]),{'status':'SUSPENDED'}).status_code,403)

    def test_superuser_can_read_global_users_without_business_membership(self):
        self.client.force_login(self.platform)
        self.assertEqual(self.client.get(reverse('controlcenter:overview')).status_code,200)
        page=self.client.get(reverse('controlcenter:users'))
        self.assertContains(page,'tenant@example.com')
        self.assertContains(page,'staff@example.com')
        self.assertEqual(self.client.get(reverse('cloud:dashboard')).status_code,302)

    def test_managed_account_status_change_audited(self):
        self.client.force_login(self.platform)
        url=reverse('controlcenter:business_update',args=[self.business.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        response=self.client.post(url,{'status':'ACTIVE','subscription_ends':'2026-12-31'})
        self.assertEqual(response.status_code,302)
        self.business.refresh_from_db()
        self.assertEqual(self.business.status,'ACTIVE')
        self.assertEqual(str(self.business.subscription_ends),'2026-12-31')
        self.assertEqual(PlatformAudit.objects.filter(company=self.business,actor=self.platform).count(),1)

    def test_platform_manager_may_disable_business_login_but_not_staff(self):
        self.client.force_login(self.platform)
        url=reverse('controlcenter:user_access_update',args=[self.owner.pk])
        response=self.client.post(url,{'account_state':'disable'})
        self.assertEqual(response.status_code,302)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)
        self.assertTrue(PlatformAudit.objects.filter(action='USER_ACCESS_UPDATED').exists())
        self.client.post(reverse('controlcenter:user_access_update',args=[self.platform.pk]),{'account_state':'disable'})
        self.platform.refresh_from_db()
        self.assertTrue(self.platform.is_active)
        self.client.post(reverse('controlcenter:user_access_update',args=[self.staff.pk]),{'account_state':'disable'})
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

class WorldLinkTeamOnboardingTests(TestCase):
    """Protect staff onboarding and prevent public/tenant privilege escalation."""
    def setUp(self):
        from .services import set_staff_role
        self.owner = User.objects.create_superuser(username='wl-owner@example.com',
            email='wl-owner@example.com',password='UniqueOwnerPassword123!')
        self.manager = User.objects.create_user(username='manager@example.com',
            email='manager@example.com', password='UniqueManagerPassword123!', is_staff=True)
        set_staff_role(self.manager, 'MANAGER')
        self.support = User.objects.create_user(username='support@example.com',
            email='support@example.com', password='UniqueSupportPassword123!', is_staff=True)
        set_staff_role(self.support, 'SUPPORT')
        self.business = Company.objects.create(name='Arusha Operator')
        self.business_user = User.objects.create_user(username='customer@example.com',
            email='customer@example.com', password='UniqueCustomerPassword123!')
        Membership.objects.create(company=self.business, user=self.business_user,role='OWNER')

    def test_two_login_portals_and_staff_only_routes(self):
        resp = self.client.get(reverse('login')+'?portal=staff')
        self.assertContains(resp, 'WorldLink team')
        self.assertNotContains(resp, 'Create an account')
        self.assertEqual(self.client.post(reverse('login'), {
            'username':self.business_user.username,'password':'UniqueCustomerPassword123!',
            'portal':'staff'}).status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        response = self.client.post(reverse('login'), {
            'username':self.support.username,'password':'UniqueSupportPassword123!',
            'portal':'staff'})
        self.assertRedirects(response, reverse('controlcenter:overview'),fetch_redirect_response=False)
        self.client.logout()
        self.assertEqual(self.client.post(reverse('login'), {
            'username':self.support.username,'password':'UniqueSupportPassword123!',
            'portal':'business'}).status_code,200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_support_can_view_but_not_manage_or_invite(self):
        self.client.force_login(self.support)
        self.assertEqual(self.client.get(reverse('controlcenter:overview')).status_code,200)
        self.assertEqual(self.client.get(reverse('controlcenter:team')).status_code,200)
        self.assertEqual(self.client.get(reverse('controlcenter:staff_invite')).status_code,403)
        self.assertEqual(self.client.post(reverse('controlcenter:business_create'),{'name':'Bad'}).status_code,403)
        self.assertEqual(self.client.post(reverse('controlcenter:branding_update'),{'name':'Bad'}).status_code,403)
        self.assertEqual(self.client.get(reverse('cloud:dashboard')).status_code,302)

    def test_manager_cannot_invite_manager_or_promote_self(self):
        self.client.force_login(self.manager)
        resp=self.client.post(reverse('controlcenter:staff_invite'), {
            'name':'Another Manager','email':'someone@example.com','role':'MANAGER'})
        self.assertEqual(resp.status_code,200)
        self.assertFalse(User.objects.filter(username='someone@example.com').exists())
        resp=self.client.post(reverse('controlcenter:staff_invite'), {
            'name':'New Support','email':'new-support@example.com','role':'SUPPORT'})
        self.assertRedirects(resp, reverse('controlcenter:invitation_created'),fetch_redirect_response=False)
        new_user=User.objects.get(username='new-support@example.com')
        self.assertFalse(new_user.is_active)
        self.assertFalse(new_user.has_usable_password())
        # Django intentionally denies effective permissions to inactive accounts,
        # even when the permissions are already assigned for future activation.
        self.assertFalse(new_user.has_perm('cloud.view_platform_console'))
        self.assertTrue(new_user.user_permissions.filter(
            content_type__app_label='cloud', codename='view_platform_console'
        ).exists())
        self.assertFalse(new_user.user_permissions.filter(
            content_type__app_label='cloud', codename='manage_platform_console'
        ).exists())
        self.assertEqual(self.client.post(reverse('controlcenter:staff_update', args=[self.manager.pk]), {'action':'role','role':'SUPPORT'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('controlcenter:staff_update', args=[self.owner.pk]), {'action':'disable'}).status_code,403)
        self.assertEqual(self.client.post(reverse('controlcenter:staff_update', args=[new_user.pk]), {'action':'role','role':'MANAGER'}).status_code,403)

    def test_invitation_one_time_and_activation(self):
        from .models import AccessInvitation
        self.client.force_login(self.owner)
        response=self.client.post(reverse('controlcenter:staff_invite'),{
            'name':'Test Person','email':'staff-invited@example.com','role':'MANAGER'})
        self.assertEqual(response.status_code,302)
        invite=AccessInvitation.objects.get(user__username='staff-invited@example.com')
        self.assertEqual(invite.purpose, 'STAFF')
        link=self.client.session['wl_recent_invite']['link']
        from urllib.parse import urlsplit
        path=urlsplit(link).path
        self.assertNotIn('staff-invited@example.com', link)
        self.assertNotIn(link.rsplit('/',2)[-2],invite.token_digest)
        self.client.logout()
        self.assertEqual(self.client.get(path).status_code,200)
        accept=self.client.post(path, {'new_password1':'BrandNewPassword123!',
            'new_password2':'BrandNewPassword123!'})
        self.assertEqual(accept.status_code,302)
        person=User.objects.get(username='staff-invited@example.com')
        self.assertTrue(person.is_active)
        self.assertTrue(person.check_password('BrandNewPassword123!'))
        # Once activated, the invited manager has the intended effective role.
        self.assertTrue(person.has_perm('cloud.view_platform_console'))
        self.assertTrue(person.has_perm('cloud.manage_platform_console'))
        self.assertEqual(self.client.get(path).status_code,404)
        invite.refresh_from_db()
        self.assertIsNotNone(invite.accepted_at)
        self.assertTrue(PlatformAudit.objects.filter(action='INVITATION_ACCEPTED').exists())

    def test_business_creation_and_private_owner_invite(self):
        from .models import AccessInvitation
        self.client.force_login(self.owner)
        response=self.client.post(reverse('controlcenter:business_create'),{
            'name':'Moshi New WiFi','status':'TRIAL','subscription_ends':''})
        self.assertEqual(response.status_code,302)
        company=Company.objects.get(name='Moshi New WiFi')
        resp=self.client.post(reverse('controlcenter:business_invite_owner',args=[company.pk]),{
            'name':'Operator Owner','email':'operator-new@example.com'})
        self.assertEqual(resp.status_code,302)
        person=User.objects.get(username='operator-new@example.com')
        self.assertFalse(person.is_staff)
        self.assertFalse(person.is_active)
        self.assertTrue(Membership.objects.filter(user=person,company=company,role='OWNER').exists())
        self.assertEqual(AccessInvitation.objects.get(user=person).purpose, 'BUSINESS')

    def test_tenant_cannot_open_team_or_branding(self):
        self.client.force_login(self.business_user)
        for route in ('controlcenter:overview','controlcenter:team','controlcenter:branding',
                      'controlcenter:staff_invite','controlcenter:business_create'):
            self.assertEqual(self.client.get(reverse(route)).status_code,403)


    def test_global_hotspot_directory_requires_platform_permission(self):
        from hotspots.models import HotspotCustomer
        HotspotCustomer.objects.create(company=self.business, full_name='Pilot Customer', phone='0700000000')
        self.client.force_login(self.support)
        page = self.client.get(reverse('controlcenter:platform_customers'))
        self.assertContains(page, 'Pilot Customer')
        self.assertEqual(self.client.get(reverse('controlcenter:platform_sessions')).status_code,200)
        self.client.force_login(self.business_user)
        self.assertEqual(self.client.get(reverse('controlcenter:platform_customers')).status_code,403)
        self.assertEqual(self.client.get(reverse('controlcenter:platform_sessions')).status_code,403)
