import logging

from .celery_app import celery_app
from .services import placements as placements_service
from .services import purge as purge_service
from .services import sale_events as sale_events_service
from .services import tontine as tontine_service
from .celery_app import record_task

@celery_app.task(name='tontine.create_cycle_and_assign_payout')
def create_cycle_and_assign_payout(group_id):
    """Create a tontine cycle in a worker process."""
    try:
        result = tontine_service.create_cycle_and_assign_payout_sync(group_id)
        record_task('tontine.create_cycle_and_assign_payout', 'success')
        return result
    except Exception:
        record_task('tontine.create_cycle_and_assign_payout', 'failure')
        raise

@celery_app.task(name='tontine.close_due_cycles')
def close_due_cycles_task():
    try:
        result = tontine_service.close_due_cycles_sync()
        record_task('tontine.close_due_cycles', 'success')
        return result
    except Exception:
        record_task('tontine.close_due_cycles', 'failure')
        raise


@celery_app.task
def send_webhook_processing_event(external_id: str):
    """Placeholder task to process webhook events asynchronously."""
    try:
        tontine_service.process_webhook_sync(external_id)
        record_task('send_webhook_processing_event', 'success')
    except Exception:
        record_task('send_webhook_processing_event', 'failure')
        raise


@celery_app.task(name='placements.expire_finished')
def expire_finished_placements_task():
    """Drop finished featured-slot campaigns out of the carousel."""
    try:
        result = placements_service.expire_finished_placements_sync()
        record_task('placements.expire_finished', 'success')
        return result
    except Exception:
        record_task('placements.expire_finished', 'failure')
        raise


@celery_app.task(name='sale_events.report_quarantine')
def report_quarantine_task():
    """Keep the unresolved backfill backlog visible.

    Migration 0014 quarantined declared sales it could not attach to a venue
    rather than guessing one. Those are real amounts belonging to nobody we can
    name, excluded from every revenue figure -- so the count has to stay in front
    of someone until it is zero.
    """
    try:
        result = sale_events_service.quarantine_summary_sync()
        if result['quarantined']:
            logging.getLogger('fidelia.sale_events').warning(
                'sale_events quarantine: %s unresolved declared sales totalling %s -- '
                'resolve via GET /api/admin/sale-events/quarantined',
                result['quarantined'], result['amount'],
            )
        record_task('sale_events.report_quarantine', 'success')
        return result
    except Exception:
        record_task('sale_events.report_quarantine', 'failure')
        raise


@celery_app.task(name='maintenance.purge_expired')
def purge_expired_task():
    """Delete spent sign-in codes, dead sessions and old app error reports."""
    try:
        result = purge_service.purge_expired_sync()
        logging.getLogger('fidelia.purge').info('purge_expired: %s', result)
        record_task('maintenance.purge_expired', 'success')
        return result
    except Exception:
        record_task('maintenance.purge_expired', 'failure')
        raise
