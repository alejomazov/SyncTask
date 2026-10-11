from enum import StrEnum


class AuditAction(StrEnum):
    AUTH_REGISTER = "auth.register"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    AUTH_LOGOUT = "auth.logout"
    ADMIN_USER_CREATED = "admin.user_created"
    ADMIN_USER_ENABLED = "admin.user_enabled"
    ADMIN_USER_DISABLED = "admin.user_disabled"
    CONNECTION_CONNECTED = "connection.connected"
    CONNECTION_FAILED = "connection.failed"
    CONNECTION_DISCONNECTED = "connection.disconnected"
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_COMPLETED = "task.completed"
    TASK_REOPENED = "task.reopened"
    TASK_DELETED = "task.deleted"
