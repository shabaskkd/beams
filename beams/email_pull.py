import frappe
import time

def email_pull_job(**kwargs):
    lock_name = "email_pull_lock"

    # get redis connection
    redis_conn = frappe.cache()

    # try to acquire lock
    if redis_conn.get(lock_name):
        return  # already running

    try:
        # set lock (expire in 30 sec)
        redis_conn.set(lock_name, "locked", ex=30)

        print("=== Email Pull Job Running ===")

        frappe.get_doc("Email Account", "Suport").receive()

        time.sleep(10)

        frappe.enqueue(
            "beams.email_pull.email_pull_job",
            queue="short",
            timeout=300
        )

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Email Pull Error")

    finally:
        # release lock
        redis_conn.delete(lock_name)
