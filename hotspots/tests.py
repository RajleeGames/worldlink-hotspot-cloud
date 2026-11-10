from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from tenants.models import Company, Membership
from networks.models import Location, Router, WifiPlan
from .models import HotspotCustomer, HotspotSession

User=get_user_model()

class HotspotAccessTests(TestCase):
    def setUp(self):
        self.a=Company.objects.create(name='Operator A')
        self.b=Company.objects.create(name='Operator B')
        self.owner=User.objects.create_user(username='owner-hot@example.com',password='securePassword124!')
        self.other=User.objects.create_user(username='other-hot@example.com',password='securePassword124!')
        Membership.objects.create(user=self.owner,company=self.a,role='OWNER')
        Membership.objects.create(user=self.other,company=self.b,role='OWNER')
        self.loc_a=Location.objects.create(company=self.a,name='Main site')
        self.loc_b=Location.objects.create(company=self.b,name='Private site')
        self.ra=Router.objects.create(company=self.a,location=self.loc_a,name='Router A')
        self.rb=Router.objects.create(company=self.b,location=self.loc_b,name='Router B')
        self.pa=WifiPlan.objects.create(company=self.a,name='Package A',duration_minutes=90,price=500)
        self.pb=WifiPlan.objects.create(company=self.b,name='Private Plan',duration_minutes=60,price=1200)
        self.ca=HotspotCustomer.objects.create(company=self.a,full_name='Alice Test',phone='070000001')
        self.cb=HotspotCustomer.objects.create(company=self.b,full_name='PRIVATE OTHER CUSTOMER',phone='070000099')
        self.sa=HotspotSession.objects.create(company=self.a,customer=self.ca,router=self.ra,plan=self.pa,
                username='alice',source='DEMO',status='ACTIVE',expires_at=timezone.now()+timedelta(minutes=20))
        self.sb=HotspotSession.objects.create(company=self.b,customer=self.cb,router=self.rb,plan=self.pb,
                username='secret',source='DEMO',expires_at=timezone.now()+timedelta(minutes=15))

    def test_business_session_and_customer_isolation(self):
        self.client.force_login(self.owner)
        page=self.client.get(reverse('hotspots:sessions'))
        self.assertEqual(page.status_code,200)
        self.assertNotContains(page,'PRIVATE OTHER CUSTOMER')
        self.assertEqual(page.context['stats']['online_count'],0)
        self.assertContains(page,'Demo')
        self.assertEqual(self.client.get(reverse('hotspots:session_detail',args=[self.sb.pk])).status_code,404)
        self.assertEqual(self.client.get(reverse('hotspots:customer_detail',args=[self.cb.pk])).status_code,404)
        self.assertEqual(self.client.post(reverse('hotspots:customer_delete',args=[self.cb.pk])).status_code,404)
        self.assertNotContains(self.client.get(reverse('hotspots:customers')),'PRIVATE OTHER CUSTOMER')
        self.assertNotIn(b'PRIVATE OTHER CUSTOMER',self.client.get(reverse('hotspots:sessions_export')).content)

    def test_observed_online_requires_recent_heartbeat_and_real_source(self):
        self.assertFalse(self.sa.online)
        self.assertFalse(self.sb.online)
        self.sa.source='RADIUS';self.sa.last_seen_at=timezone.now();self.sa.save()
        self.assertTrue(self.sa.online)
        self.sa.last_seen_at=timezone.now()-timedelta(minutes=8);self.sa.save()
        self.assertFalse(self.sa.online)
        self.sa.last_seen_at=timezone.now();self.sa.expires_at=timezone.now()-timedelta(minutes=1);self.sa.save()
        self.assertFalse(self.sa.online)

    def test_wrong_tenant_model_validation(self):
        self.sa.plan=self.pb
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):self.sa.full_clean()

    def test_customer_create_and_history_deletion_guard(self):
        self.client.force_login(self.owner)
        result=self.client.post(reverse('hotspots:customer_new'),{'full_name':'New Customer','phone':'0712345678','email':'','notes':''})
        self.assertEqual(result.status_code,302)
        created=HotspotCustomer.objects.get(full_name='New Customer')
        self.assertEqual(created.company,self.a)
        self.client.post(reverse('hotspots:customer_delete',args=[self.ca.pk]))
        self.assertTrue(HotspotCustomer.objects.filter(pk=self.ca.pk).exists())
        self.client.post(reverse('hotspots:customer_delete',args=[created.pk]))
        self.assertFalse(HotspotCustomer.objects.filter(pk=created.pk).exists())

    def test_cashier_can_create_customer_but_not_delete(self):
        Membership.objects.filter(user=self.owner).update(role='CASHIER')
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('hotspots:customer_delete',args=[self.ca.pk])).status_code,403)
        self.assertEqual(self.client.post(reverse('hotspots:customer_new'),{'full_name':'Store guest'}).status_code,302)

    def test_anonymous_cannot_read_sessions(self):
        response=self.client.get(reverse('hotspots:sessions'))
        self.assertEqual(response.status_code,302)
        self.assertIn('/login/',response['Location'])

class AdapterServiceTests(TestCase):
    def setUp(self):
        self.a=Company.objects.create(name='A Site')
        self.b=Company.objects.create(name='B Site')
        self.la=Location.objects.create(company=self.a,name='Main')
        self.lb=Location.objects.create(company=self.b,name='Main')
        self.ra=Router.objects.create(company=self.a,location=self.la,name='A Router')
        self.rb=Router.objects.create(company=self.b,location=self.lb,name='B Router')
        self.pa=WifiPlan.objects.create(company=self.a,name='60 mins',duration_minutes=60,price=400)
        self.pb=WifiPlan.objects.create(company=self.b,name='60 mins',duration_minutes=60,price=400)

    def test_upsert_is_idempotent_and_tenant_validated(self):
        from .services import record_authenticated_observation
        from django.core.exceptions import ValidationError
        now=timezone.now()
        data={'company':self.a,'router':self.ra,'plan':self.pa,'external_id':'server-session-1',
            'source':'RADIUS','started_at':now-timedelta(minutes=1),'last_seen_at':now,
            'expires_at':now+timedelta(minutes=59),'bytes_download':500}
        item=record_authenticated_observation(**data)
        self.assertTrue(item.online)
        again=record_authenticated_observation(**{**data,'bytes_download':1000})
        self.assertEqual(item.pk,again.pk)
        self.assertEqual(again.bytes_download,1000)
        self.assertEqual(HotspotSession.objects.count(),1)
        with self.assertRaises(ValidationError):record_authenticated_observation(**{**data,'plan':self.pb,'external_id':'invalid'})
        with self.assertRaises(ValidationError):record_authenticated_observation(**{**data,'source':'DEMO','external_id':'invalid'})
