"""Reusable admin CRUD helper functions for list, save, soft-delete, and restore workflows."""
from typing import Callable, Any, Optional
from flask import render_template, redirect, flash, request, abort
from flask_login import current_user
from sqlalchemy import select, or_

from app.extensions import db
from app.common.audit import log_audit_event
from app.admin.forms import EmptyActionForm


def render_admin_list(
    model: Any,
    template_name: str,
    search_columns: list[Any],
    context_extra: Optional[dict[str, Any]] = None,
    base_filter: Optional[Any] = None,
    order_by_col: Optional[Any] = None,
    per_page: int = 15,
):
    """Generic search, filter, and pagination renderer for admin list views."""
    page = request.args.get("page", 1, type=int)
    search_query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all")

    stmt = select(model)

    if base_filter is not None:
        stmt = stmt.filter(base_filter)

    if hasattr(model, "is_deleted"):
        if status_filter == "active":
            stmt = stmt.filter(model.is_deleted == False)
        elif status_filter == "deleted":
            stmt = stmt.filter(model.is_deleted == True)

    if search_query and search_columns:
        like_expr = f"%{search_query}%"
        stmt = stmt.filter(or_(*[col.ilike(like_expr) for col in search_columns]))

    if order_by_col is not None:
        stmt = stmt.order_by(order_by_col)
    else:
        stmt = stmt.order_by(model.id.asc())

    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    action_form = EmptyActionForm()

    ctx = {
        "pagination": pagination,
        "search_query": search_query,
        "status_filter": status_filter,
        "action_form": action_form,
        "extra_args": {"q": search_query, "status": status_filter},
    }
    if context_extra:
        ctx.update(context_extra)

    return render_template(template_name, **ctx)


def handle_admin_soft_delete(
    instance: Any,
    redirect_url: str,
    entity_name: str,
    identifier_str: str,
    block_check: Optional[Callable[[], Optional[str]]] = None,
):
    """Execute a soft-delete mutation with active children guard and atomic audit logging."""
    form = EmptyActionForm()
    if not form.validate_on_submit():
        flash("Invalid security token for delete operation.", "danger")
        return redirect(redirect_url)

    if block_check:
        block_reason = block_check()
        if block_reason:
            flash(block_reason, "danger")
            return redirect(redirect_url)

    old_values = {"is_deleted": False}
    instance.soft_delete(user_id=current_user.id)

    log_audit_event(
        action=f"SOFT_DELETE_{entity_name.upper()}",
        entity_name=entity_name,
        entity_id=instance.id,
        user_id=current_user.id,
        old_values=old_values,
        new_values={"is_deleted": True, "deleted_by_id": current_user.id},
    )
    db.session.commit()

    flash(f"{entity_name} '{identifier_str}' has been soft-deleted successfully.", "warning")
    return redirect(redirect_url)


def handle_admin_restore(
    instance: Any,
    redirect_url: str,
    entity_name: str,
    identifier_str: str,
):
    """Execute a restore mutation on a soft-deleted entity with atomic audit logging."""
    form = EmptyActionForm()
    if not form.validate_on_submit():
        flash("Invalid security token for restore operation.", "danger")
        return redirect(redirect_url)

    old_values = {"is_deleted": True}
    instance.restore()

    log_audit_event(
        action=f"RESTORE_{entity_name.upper()}",
        entity_name=entity_name,
        entity_id=instance.id,
        user_id=current_user.id,
        old_values=old_values,
        new_values={"is_deleted": False},
    )
    db.session.commit()

    flash(f"{entity_name} '{identifier_str}' has been restored successfully.", "success")
    return redirect(redirect_url)


def handle_admin_hard_delete(
    instance: Any,
    redirect_url: str,
    entity_name: str,
    identifier_str: str,
    block_check: Optional[Callable[[], Optional[str]]] = None,
):
    """Execute a hard-delete mutation with active children/dependencies guard and audit logging."""
    form = EmptyActionForm()
    if not form.validate_on_submit():
        flash("Invalid security token for delete operation.", "danger")
        return redirect(redirect_url)

    if block_check:
        block_reason = block_check()
        if block_reason:
            flash(block_reason, "danger")
            return redirect(redirect_url)

    inst_id = instance.id
    db.session.delete(instance)

    log_audit_event(
        action=f"DELETE_{entity_name.upper()}",
        entity_name=entity_name,
        entity_id=inst_id,
        user_id=current_user.id,
        new_values={"deleted": True},
    )
    db.session.commit()

    flash(f"{entity_name} '{identifier_str}' has been deleted successfully.", "warning")
    return redirect(redirect_url)


