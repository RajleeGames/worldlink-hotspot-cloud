"""Read-only central-controller observations for staff-approved tenant APs."""

import time

from django.core.management.base import BaseCommand, CommandError

from networks.omada_monitor import OmadaMonitorError, poll_approved_managed


class Command(BaseCommand):
    help = 'Check WorldLink-approved central Omada APs. Never changes the controller or activates Wi-Fi.'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true')
        parser.add_argument('--interval', type=int, default=30)
        parser.add_argument('--limit', type=int, default=50)

    def handle(self, *args, **options):
        if not 15 <= options['interval'] <= 300:
            raise CommandError('Poll interval must be between 15 and 300 seconds.')
        if not 1 <= options['limit'] <= 200:
            raise CommandError('Router limit must be between 1 and 200.')
        while True:
            try:
                observations = poll_approved_managed(limit=options['limit'])
                self.stdout.write(f'Checked {len(observations)} WorldLink-managed Omada AP(s).')
                for item in observations:
                    self.stdout.write(f'AP #{item.router_id}: {item.get_state_display()} '
                                      f'({item.checked_at:%Y-%m-%d %H:%M:%S} UTC).')
            except OmadaMonitorError as exc:
                if not options['loop']:
                    raise CommandError(str(exc)) from exc
                self.stderr.write(f'Central Omada read-only poll: {exc}')
            if not options['loop']:
                return
            time.sleep(options['interval'])
