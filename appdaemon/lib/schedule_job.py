import traceback
from datetime import datetime

SCHEDULED_HANDLES = {}


def schedule_job(app, callback, delay, trigger_info=None):
    cancel_job(app, trigger_info)

    job_name = build_job_name(app, trigger_info)
    SCHEDULED_HANDLES[job_name] = app.run_in(callback, delay, trigger_info=trigger_info)

    app.log('Scheduled job to run in {} seconds, job_name={}'.format(delay, job_name))


def schedule_jobs(app, jobs, trigger_info=None):
    cancel_job(app, trigger_info)

    for job_name, job in jobs.items():
        SCHEDULED_HANDLES[job_name] = app.run_in(job['callback'], job['delay'], trigger_info=trigger_info)

        app.log('Scheduled job to run in {} seconds, job_name={}'.format(job['delay'], job_name))


def schedule_repeat_job(app, callback, start, delay, trigger_info=None):
    cancel_job(app, trigger_info)

    job_name = build_job_name(app, trigger_info)
    SCHEDULED_HANDLES[job_name] = app.run_every(callback, start, delay, trigger_info=trigger_info)

    app.log('Scheduled job to run at {} and repeat every {} seconds, job_name={}'.format(
        start,
        delay,
        job_name))


def cancel_job(app, trigger_info=None):
    target_job_name = build_job_name(app, trigger_info)
    if target_job_name is None:
        return

    existing_job_names = list(SCHEDULED_HANDLES.keys())

    app.debug('cancelling job ... existing_job_names={}, target_job_name={}'.format(
        existing_job_names,
        target_job_name))

    for job_name in existing_job_names:
        if job_name.startswith(target_job_name):
            app.debug('About to cancel job: {}'.format(job_name))

            try:
                app.cancel_timer(SCHEDULED_HANDLES[job_name])
                SCHEDULED_HANDLES.pop(job_name, None)
                app.log('Cancelled job: {}'.format(job_name))
            except:
                app.error('Error when cancel job: ' + traceback.format_exc())


def build_job_name(app, trigger_info=None):
    if not trigger_info:
        app.debug('trigger_info is None, set job_name={}'.format(app.name))
        return app.name
    elif trigger_info.platform != 'state':
        app.debug('trigger_info.platform is {}, set job_name={}'.format(trigger_info.platform, app.name))
        return app.name

    triggered_entity_id = trigger_info.data['entity_id']
    if not triggered_entity_id:
        app.debug('triggered_entity_id is None, set job_name={}'.format(app.name))
        return app.name

    app_name = '{}_{}'.format(app.name, triggered_entity_id)
    app.debug('built job_name={}'.format(app_name))
    return app_name


def find_scheduled_jobs(app):
    jobs = {}
    for job_name, handle in SCHEDULED_HANDLES.items():
        if job_name.startswith(app.name):
            jobs[job_name] = handle

    return jobs


def has_scheduled_job(app):
    jobs = find_scheduled_jobs(app)

    for handle in jobs.values():
        if handle is None:
            continue

        try:
            scheduled_time, interval, kwargs = app.info_timer(handle)

            # if job is already run, check if it's repeatable job or not
            if datetime.now() > scheduled_time:
                if interval != 0:
                    return True
                else:
                    continue

            return True
        except (ValueError, TypeError):
            app.debug('Unknown handle: {} in {}\n{}'.format(handle, jobs, traceback.format_exc()))

    return False
