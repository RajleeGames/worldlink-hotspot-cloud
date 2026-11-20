"""WorldLink server operator convenience: list site IDs from official Open API."""

from django.core.management.base import BaseCommand, CommandError

from networks.omada_monitor import OmadaMonitorError, OmadaReadOnlyClient


class Command(BaseCommand):
    help = 'Read-only list of visible Omada site names and their Open API site IDs.'

    def handle(self, *args, **options):
        try:
            sites = OmadaReadOnlyClient().visible_sites()
        except OmadaMonitorError as exc:
            raise CommandError(str(exc)) from exc
        for site in sites:
            site_id = site.get('siteId', site.get('id', ''))
            site_name = site.get('name', site.get('siteName', 'Unnamed site'))
            self.stdout.write(f'{str(site_name)[:120]}: {str(site_id)[:80]}')
        self.stdout.write(f'{len(sites)} visible Omada site(s).')
