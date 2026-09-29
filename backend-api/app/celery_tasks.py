from .celery_app import celery_app
from .services import placements as placements_service
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
