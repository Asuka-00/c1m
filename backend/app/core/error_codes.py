"""错误码注册表（唯一来源）。

后端只返回错误码与参数（``{code, message, params}``，``message`` 为英文兜底），
各语言文案在前端 ``locales/<语言>/error.yaml`` 的 ``error.code_<错误码>``；
带 ``{{field}}`` 的文案由前端填入字段显示名。新增错误码：在对应段追加常量，
再补前端三语文案（``pnpm i18n:check`` 会校验）。

分段：
- 100000-109999  系统与通用
- 200000-209999  认证与平台（用户、租户、角色、权限、菜单、文件、通知）
- 300000-309999  系统配置
- 400000-409999  MES 主数据（通用、工厂、产品、工艺）
- 500000-509999  MES 设备与质量
- 600000-609999  MES 批次、工单与入库
- 700000-709999  MES 执行（作业、Hold、批量、载具、追溯、交接班）
"""

from typing import Final

# ==================== 系统与通用 100000-109999 ====================

SORT_BY_INVALID: Final = 100001  # Sort field must be one of: {allowed}
UNKNOWN_ENTITY: Final = 100002  # Unknown entity
DUPLICATE_KEY: Final = 100003  # A record with the same key already exists
RECORD_REFERENCED: Final = 100004  # Record is referenced by other records
CONSTRAINT_VIOLATION: Final = 100005  # Constraint violation
READ_ONLY_ENTITY: Final = 100006  # Read-only entity
NOT_A_VALID_XLSX_FILE: Final = 100007  # Not a valid xlsx file
EMPTY_SHEET: Final = 100008  # Empty sheet
IMPORT_UNKNOWN_COLUMNS: Final = 100009  # Unknown columns: {columns}
IMPORT_TOO_MANY_ROWS: Final = 100010  # Too many rows (max {max})
REF_VALUE_NOT_FOUND: Final = 100011  # '{value}' not found
INVALID_UUID: Final = 100012  # Invalid ID
INVALID_DATE: Final = 100013  # Invalid date
RECORD_NOT_FOUND: Final = 100014  # Record not found
FILTER_NOT_TEXT: Final = 100015  # {name} is not a text filter
ENTITY_IS_NOT_HIERARCHICAL: Final = 100016  # Entity is not hierarchical
STR_TOO_LONG: Final = 100017  # At most {max} characters
NOT_INTEGER: Final = 100018  # Must be an integer
NOT_NUMBER: Final = 100019  # Must be a number
NOT_BOOL: Final = 100020  # Must be true or false
NOT_IN_ENUM: Final = 100021  # Must be one of: {allowed}
FIELD_REQUIRED: Final = 100022  # Required
FIELD_REQUIRED_WHEN: Final = 100023  # Required when {when} = {value}
FIELD_REF_NOT_FOUND: Final = 100024  # Referenced record not found
PARENT_CYCLE: Final = 100025  # The parent would create a cycle
ATTRS_NOT_OBJECT: Final = 100026  # Custom attributes must be an object
ATTR_UNKNOWN: Final = 100027  # Unknown attribute {attr}
ATTR_REQUIRED: Final = 100028  # {name} is required
ATTR_INVALID: Final = 100029  # {name}: invalid {type} value
VERSION_NOT_DRAFT: Final = (
    100030  # Only draft versions can be changed; create a new version
)
PARENT_NOT_DRAFT: Final = (
    100031  # The parent mes.entity.{entity}) is not a draft; create a new version first
)
ENTITY_IS_NOT_VERSIONED: Final = 100032  # Entity is not versioned
STATUS_INVALID: Final = 100033  # Status must be one of: {allowed}
STATUS_TRANSITION: Final = (
    100034  # Cannot change status from mes.enum.status.{src}) to mes.enum.status.{to})
)
PERMISSION_DENIED: Final = 100035  # Not enough permissions
FILE_TOO_LARGE: Final = 100036  # File too large
FIELD_RANGE: Final = 100037  # Must be between {min} and {max}
FIELD_MIN: Final = 100038  # Must be at least {min}
FIELD_GT: Final = 100039  # Must be greater than {min}
LOT_STATUS: Final = 100040  # lot status
ON_HOLD: Final = 100041  # on hold
USL_GE_LSL: Final = 100042  # Must be at least the lower spec limit
TARGET_WITHIN_LIMITS: Final = 100043  # Must lie within the spec limits
TENANT_NOT_FOUND: Final = 100044  # Tenant not found
PYD_MISSING: Final = 100200  # Required
PYD_EXTRA_FORBIDDEN: Final = 100201  # Unsupported field
PYD_STRING_TYPE: Final = 100202  # Must be text
PYD_INT_TYPE: Final = 100203  # Must be an integer
PYD_INT_PARSING: Final = 100204  # Must be an integer
PYD_INT_FROM_FLOAT: Final = 100205  # Must be an integer
PYD_FLOAT_TYPE: Final = 100206  # Must be a number
PYD_FLOAT_PARSING: Final = 100207  # Must be a number
PYD_DECIMAL_TYPE: Final = 100208  # Must be a number
PYD_DECIMAL_PARSING: Final = 100209  # Must be a number
PYD_BOOL_TYPE: Final = 100210  # Must be true or false
PYD_BOOL_PARSING: Final = 100211  # Must be true or false
PYD_UUID_TYPE: Final = 100212  # Invalid ID
PYD_UUID_PARSING: Final = 100213  # Invalid ID
PYD_DATE_TYPE: Final = 100214  # Invalid date
PYD_DATE_PARSING: Final = 100215  # Invalid date
PYD_DATE_FROM_DATETIME_PARSING: Final = 100216  # Invalid date
PYD_DATETIME_TYPE: Final = 100217  # Invalid date and time
PYD_DATETIME_PARSING: Final = 100218  # Invalid date and time
PYD_TIME_TYPE: Final = 100219  # Invalid time
PYD_TIME_PARSING: Final = 100220  # Invalid time
PYD_STRING_TOO_SHORT: Final = 100221  # At least {min_length} characters
PYD_STRING_TOO_LONG: Final = 100222  # At most {max_length} characters
PYD_STRING_PATTERN_MISMATCH: Final = 100223  # Invalid format
PYD_GREATER_THAN: Final = 100224  # Must be greater than {gt}
PYD_GREATER_THAN_EQUAL: Final = 100225  # Must be at least {ge}
PYD_LESS_THAN: Final = 100226  # Must be less than {lt}
PYD_LESS_THAN_EQUAL: Final = 100227  # Must be at most {le}
PYD_TOO_SHORT: Final = 100228  # At least {min_length} items
PYD_TOO_LONG: Final = 100229  # At most {max_length} items
PYD_LITERAL_ERROR: Final = 100230  # Must be one of: {expected}
PYD_ENUM: Final = 100231  # Must be one of: {expected}
PYD_JSON_INVALID: Final = 100232  # Invalid JSON
PYD_DICT_TYPE: Final = 100233  # Must be an object
PYD_MODEL_ATTRIBUTES_TYPE: Final = 100234  # Must be an object
PYD_MODEL_TYPE: Final = 100235  # Must be an object
PYD_LIST_TYPE: Final = 100236  # Must be a list
PYD_URL_PARSING: Final = 100237  # Invalid URL
PYD_URL_TYPE: Final = 100238  # Invalid URL
PYD_VALUE_ERROR: Final = 100239  # Invalid value
PYD_ASSERTION_ERROR: Final = 100240  # Invalid value
PYD_INVALID: Final = 100241  # Invalid value
INVALID_TIME: Final = 100045  # Invalid time
INVALID_DATETIME: Final = 100046  # Invalid date and time
FIELD_INVALID: Final = 100047  # Invalid value

# ==================== 认证与平台（用户、租户、角色、权限、菜单、文件、通知） 200000-209999 ====================

COULD_NOT_VALIDATE_CREDENTIALS: Final = 200001  # Could not validate credentials
USER_NOT_FOUND: Final = 200002  # User not found
INACTIVE_USER: Final = 200003  # Inactive user
USER_PRIVILEGES_INSUFFICIENT: Final = 200004  # The user doesn't have enough privileges
TENANT_IS_SUSPENDED: Final = 200005  # Tenant is suspended
TENANT_HAS_EXPIRED: Final = 200006  # Tenant has expired
IMPERSONATION_TENANT_MISMATCH: Final = (
    200007  # Impersonation token is bound to another tenant
)
TENANT_HEADER_REQUIRED: Final = (
    200008  # X-Tenant-ID header is required (user belongs to multiple or no tenants
)
EXIT_IMPERSONATION_FIRST: Final = (
    200009  # Exit tenant impersonation to use the platform console
)
INCORRECT_USERNAME_OR_PASSWORD: Final = 200010  # Incorrect username or password
INVALID_TOKEN: Final = 200011  # Invalid token
USERNAME_NOT_FOUND: Final = (
    200012  # The user with this username does not exist in the system
)
TENANT_SLUG_ALREADY_EXISTS: Final = 200013  # Tenant slug already exists
OWNER_USER_NOT_FOUND: Final = 200014  # Owner user not found
CHANNEL_NOT_FOUND: Final = 200015  # Channel not found
UNSUPPORTED_FILE_TYPE: Final = 200016  # Unsupported file type
EMPTY_FILE: Final = 200017  # Empty file
FILE_NOT_FOUND: Final = 200018  # File not found
NO_ACCESS_TO_THE_PLATFORM_CONSOLE: Final = 200019  # No access to the platform console
MENU_KEY_ALREADY_EXISTS: Final = 200020  # Menu key already exists
PARENT_MENU_NOT_FOUND: Final = 200021  # Parent menu not found
MENU_NOT_FOUND: Final = 200022  # Menu not found
MENU_CANNOT_BE_ITS_OWN_PARENT: Final = 200023  # Menu cannot be its own parent
SUBSCRIPTION_NOT_FOUND: Final = 200024  # Subscription not found
SUB_EVENT_UNKNOWN: Final = 200025  # Unknown event type
SUB_CHANNELS_INVALID: Final = 200026  # Unknown or empty channels: {channels}
SUB_RECIPIENTS_REQUIRED: Final = 200027  # Select at least one role or user
SCOPE_MUST_BE_PLATFORM_OR_TENANT: Final = 200028  # scope must be platform or tenant
PERM_PLATFORM_ONLY: Final = (
    200029  # Platform permission {code} cannot be assigned to a workspace
)
NOT_FOUND_NAMED: Final = 200030  # {name} not found
PERMISSION_ALREADY_EXISTS: Final = 200031  # Permission already exists
ROLE_ALREADY_EXISTS: Final = 200032  # Role already exists
PERM_NOT_FOUND: Final = 200033  # Permission {code} not found
ROLE_NOT_FOUND: Final = 200034  # Role not found
PERM_UNKNOWN: Final = 200035  # Unknown permissions: {codes}
PLATFORM_ADMIN_ONLY_STATUS: Final = (
    200036  # Only platform admins can change tenant status
)
USER_IS_ALREADY_A_MEMBER: Final = 200037  # User is already a member
OWNER_ONLY_GRANT: Final = 200038  # Only owners can grant the owner role
USER_IN_OTHER_TENANTS: Final = (
    200039  # User belongs to other tenants; ask a platform admin
)
OWNER_ONLY_MANAGE: Final = 200040  # Only owners can manage owners
MEMBER_NOT_FOUND: Final = 200041  # Member not found
OWNER_ONLY_CHANGE_ROLES: Final = 200042  # Only owners can change owner roles
TENANT_LAST_OWNER: Final = 200043  # A tenant must keep at least one owner
OWNER_ONLY_REMOVE: Final = 200044  # Only owners can remove owners
PERM_NOT_TENANT_SCOPE: Final = 200045  # Not workspace-scope permissions: {codes}
OWNER_ROLE_CANNOT_BE_RENAMED: Final = 200046  # The owner role cannot be renamed
OWNER_ROLE_CANNOT_BE_DISABLED: Final = 200047  # The owner role cannot be disabled
OWNER_ROLE_PERMISSIONS_ARE_FIXED: Final = 200048  # The owner role permissions are fixed
OWNER_ROLE_CANNOT_BE_DELETED: Final = 200049  # The owner role cannot be deleted
TENANT_ROLE_MISSING: Final = 200050  # Role '{name}' does not exist in this workspace
INCORRECT_PASSWORD: Final = 200051  # Incorrect password
PASSWORD_UNCHANGED: Final = 200052  # New password cannot be the same as the current one
SUPERUSER_SELF_DELETE: Final = (
    200053  # Super users are not allowed to delete themselves
)
USER_ID_NOT_FOUND: Final = 200054  # The user with this id does not exist in the system
SUPERUSER_ONLY: Final = 200055  # Only superusers can manage superuser accounts
USERNAME_EXISTS: Final = 200056  # User with this username already exists
EMAIL_EXISTS: Final = 200057  # User with this email already exists

# ==================== 系统配置 300000-309999 ====================

CONFIG_GROUP_NOT_FOUND: Final = 300001  # Config group not found
CFG_BAD_FILE_REF: Final = 300002  # Is not a valid file reference
CFG_FILE_NOT_OWNED: Final = 300003  # Refers to a file you do not own
CFG_UNKNOWN_ITEM: Final = 300004  # Unknown config item
CFG_NOT_OVERRIDABLE: Final = 300005  # Cannot be overridden by a workspace
CFG_NOT_STRING: Final = 300006  # Must be text
CFG_BAD_COLOR: Final = 300007  # Must be a hex color like #1e40af
CFG_BAD_URL: Final = 300008  # Must be an http(s) URL or an absolute path
CFG_BAD_OPTION: Final = 300009  # Is not one of the allowed options
FIELD_MAX: Final = 300010  # Must be at most {max}
CFG_INVALID_JSON: Final = 300011  # Is not valid JSON ({error})
CFG_UNSUPPORTED_TYPE: Final = 300012  # Has an unsupported type

# ==================== MES 主数据（通用、工厂、产品、工艺） 400000-409999 ====================

CODERULE_UNKNOWN_TOKEN: Final = 400001  # Unknown token {token} in the pattern
CODERULE_NEEDS_SEQ: Final = 400002  # The pattern needs {SEQ}, {SEQ36} or {SLOT}
CODERULE_UNBALANCED: Final = 400003  # The pattern has unbalanced braces
CODERULE_SEQ_OVERFLOW: Final = 400004  # The sequence number overflowed for this period
UOM_NO_CONVERSION: Final = 400006  # No conversion path between these units
SELECT_NEEDS_OPTIONS: Final = 400007  # A select field needs options or a dictionary
END_TIME_DIFFERS: Final = 400008  # Must differ from the start time
CROSSES_MIDNIGHT: Final = 400009  # Must be set exactly when the end is before the start
VERSION_INACTIVE: Final = 400010  # version inactive
ECN_TARGET_NOT_FOUND: Final = 400011  # ecn target not found
COPY_CODE_CONFLICT: Final = 400012  # copy code conflict
CHANGE_ORDER_NOT_FOUND: Final = 400013  # change order not found
ECN_STATUS: Final = 400014  # ecn status
ECN_NOT_EDITABLE: Final = 400015  # ecn not editable
ECN_FIELD_UNUSED: Final = 400016  # ecn field unused
ECN_NOT_DELETABLE: Final = 400017  # ecn not deletable
REWORK_ROUTE_MISSING: Final = 400018  # rework route missing
REWORK_ROUTE_EMPTY: Final = 400019  # The rework route has no steps
BRANCH_NONE: Final = 400020  # This step has no branch
BRANCH_TARGET_MISSING: Final = 400021  # Branch target seq {target} not found
ROUTE_STEP_IDS_INVALID: Final = (
    400022  # step_ids must list every step of the route exactly once
)
OPERATION_REQUIRED_FOR_STEP: Final = 400023  # Required for an operation step
SUB_ROUTE_ONLY: Final = 400024  # Only for sub-route steps
SUB_ROUTE_REQUIRED: Final = 400025  # Required for a sub-route step
SUB_ROUTE_TYPE: Final = 400026  # Must be a route of type sub
SUB_ROUTE_SELF: Final = 400027  # A route cannot call itself
REWORK_ROUTE_TYPE: Final = 400028  # Must be a route of type rework
BRANCH_CONDITION_REQUIRED: Final = 400029  # Required together with the branch target
ROUTE_ACTIVATION_STEPS: Final = (
    400030  # The route needs at least one step before activation
)
STEP_BRANCH_TARGET: Final = 400031  # Step {seq}: branch target {target} does not exist
STEP_REF_INACTIVE: Final = 400032  # Step {seq}: {code} v{version} is not active
OPERATION_OR_RECIPE: Final = 400033  # An operation or a recipe is required
SPEC_LIMIT_REQUIRED: Final = 400034  # Give a lower and/or upper spec limit
PRODUCT_ROUTE_MAIN_ONLY: Final = 400035  # Products can only bind to main routes
EFFECTIVE_TO_AFTER_FROM: Final = 400036  # Must be after the effective-from date
DEFAULT_ROUTE_EXISTS: Final = 400037  # The product already has a default route
UOM_DIFFERS: Final = 400038  # Must differ from the source unit
UOM_DIMENSIONS: Final = 400039  # The unit dimensions differ
PRODUCT_NEEDS_DEFAULT_ROUTE: Final = (
    400040  # The product needs an active default route before activation
)
STEP_FIELD_REQUIRED: Final = 400042  # Required for this resource kind
STEP_FIELD_EMPTY: Final = 400043  # Must be empty for this resource kind
ROUTE_LAYOUT_INVALID: Final = 400044  # The layout references steps outside this route
BOM_NO_LINES: Final = 400045  # Add at least one line before activating the BOM
BOM_ACTIVE_EXISTS: Final = (
    400046  # Another BOM of this product is already active: {bom}
)

# ==================== MES 设备与质量 500000-509999 ====================

EQUIPMENT_NOT_FOUND: Final = 500001  # equipment not found
E10_STATE_UNKNOWN: Final = 500002  # Unknown E10 state
E10_ALREADY: Final = 500003  # The equipment is already in {state}
E10_TRANSITION_DENIED: Final = 500004  # Transition {src} → {to} is not allowed
E10_REASON_TYPE: Final = 500005  # Select an E10 reason code
E10_REASON_REQUIRED: Final = 500006  # A reason is required for this transition
PM_PLAN_NOT_FOUND: Final = 500007  # PM plan / equipment not found
PM_PLAN_NOT_APPLICABLE: Final = 500008  # The PM plan does not apply to this equipment
EQ_TYPE_DIFFERS_RECIPE: Final = (
    500009  # The equipment type differs from the recipe's equipment type
)
E10_TO_STATE_DIFFERS: Final = (
    500010  # The target state must differ from the source state
)
INITIAL_STATE_EXISTS: Final = 500011  # {other} is already the initial state
EQ_MAIN_NO_PARENT: Final = 500012  # A main equipment cannot have a parent
EQ_NEEDS_PARENT: Final = 500013  # A mes.enum.unit_kind.{kind}) needs a parent equipment
EQ_PARENT_KIND: Final = 500014  # The parent must be a main equipment or a sub-unit
PARENT_TYPE_MISMATCH: Final = 500015  # Must match the parent equipment's type
PM_TARGET_REQUIRED: Final = 500016  # Set an equipment or an equipment type
PM_INTERVAL_REQUIRED: Final = 500017  # Set a day or lot interval
END_AFTER_START: Final = 500018  # Must be after the start time
WAFER_COUNT_RANGE: Final = 500019  # Must be 1–25 for wafer-level sampling
WAFER_SELECTION_REQUIRED: Final = 500020  # Required for wafer-level sampling
FIXED_SLOTS_FORMAT: Final = 500021  # Enter comma-separated slots 1–25
FIXED_SLOTS_COUNT: Final = 500022  # The count must equal the wafer count
MATERIAL_LOT_UNAVAILABLE: Final = 500023  # Material lot {lot} is not available
MOUNT_POSITION_BUSY: Final = (
    500024  # Position {position} already holds a material lot in this period
)

# ==================== MES 批次、工单与入库 600000-609999 ====================

LOT_BUSY: Final = 600001  # lot busy
CODE_RULE_TARGET: Final = (
    600002  # Must be a code rule for mes.enum.code_target.{target})
)
MAX_CHILDREN_MIN: Final = 600003  # Must be at least 2 when splitting is allowed
QTIME_ACTION_INVALID: Final = 600004  # qtime action invalid
STEP_OF_ROUTE: Final = 600005  # Must be a step of the selected route
STEP_AFTER_FROM: Final = 600006  # Must come after the start step
QTIME_NEED_TIME: Final = 600007  # Give a min and/or max time
QTIME_TIME_POSITIVE: Final = 600008  # The times must be positive
QTIME_MAX_GE_MIN: Final = 600009  # The max time must be at least the min time
WO_CODE_RULE_MISSING: Final = 600010  # No code rule for work orders; enter a WO number
WO_LATE_EDIT: Final = (
    600011  # Only remarks, due date and references can change after release
)
DUE_BEFORE_START: Final = 600012  # Must not be before the planned start
WO_DELETE_DRAFT_ONLY: Final = (
    600013  # Only draft work orders can be deleted (cancel instead)
)
LOT_TYPE_NOT_FOUND: Final = 600014  # Lot type not found
LOT_TYPE_RULES_MISSING: Final = (
    600015  # The lot type needs a lot ID rule and a wafer ID rule
)
ACTION_INVALID: Final = 600016  # action invalid
WO_TRANSITION: Final = 600017  # wo transition
MUST_BE_ACTIVE: Final = 600018  # Must be active
WO_ROUTE_MISSING: Final = 600019  # The product has no active default route
ROUTE_NO_STEPS: Final = 600020  # route no steps
WO_OPEN_LOTS: Final = 600021  # wo open lots
WO_LOTS_STARTED: Final = 600022  # wo lots started
LOT_SIZE_RANGE: Final = 600023  # lot size range
WO_NOT_STARTABLE: Final = 600024  # wo not startable
WO_LOTS_REQUIRED: Final = 600025  # Add at least one lot
WO_START_LIMIT: Final = 600026  # Started {started} + {total} exceeds the limit {cap} (planned {planned} + {pct}%)
LOT_QTY_RANGE: Final = 600027  # Lot {i}: qty must be 1–{max}
LOT_CARRIER_NOT_FOUND: Final = 600028  # Lot {i}: carrier not found
LOT_CARRIER_UNAVAILABLE: Final = 600029  # Lot {i}: carrier {carrier} is not available
LOT_CARRIER_IN_USE: Final = 600030  # Lot {i}: carrier {carrier} is already in use
LOT_SLOTS: Final = 600031  # Lot {i}: {n} distinct slots within 1–{width} are required
LOT_WAFER_SOURCES: Final = 600032  # Lot {i}: one source per wafer
ROUTE_NO_OPERATION_STEPS: Final = 600033  # route no operation steps
LOT_IDS_EXIST: Final = 600034  # The generated lot / wafer IDs already exist
WO_NOT_UNDOABLE: Final = 600035  # wo not undoable
NOTHING_TO_UNDO: Final = 600036  # nothing to undo
LOTS_PROCESSED: Final = 600037  # lots processed
LOT_NOT_FOUND_2: Final = 600038  # Lot not found
RECEIPT_LOT_UNFINISHED: Final = 600039  # Lot {lot} is not finished (awaiting receipt)
RECEIPT_LOT_ON_HOLD: Final = 600040  # Lot {lot} is on hold
RECEIPT_WO_STATUS: Final = (
    600041  # Work order {wo} is mes.enum.wo_status.{status}); cannot receive
)
RECEIPT_QTY_NEGATIVE: Final = 600042  # Quantities must be 0 or more
RECEIPT_QTY_ZERO: Final = 600043  # Good + scrap must be at least 1
RECEIPT_QTY_EXCEEDS: Final = 600044  # Lot {lot} has only {room} left to receive
RECEIPT_CODE_RULE_MISSING: Final = (
    600045  # No code rule for receipts; enter a receipt number
)
RECEIPT_EDIT_DRAFT_ONLY: Final = 600046  # Only draft receipts can be edited
WAREHOUSE_INACTIVE: Final = 600047  # The warehouse is inactive
LOCATION_WRONG_WAREHOUSE: Final = (
    600048  # The location does not belong to the warehouse
)
LOCATION_INACTIVE: Final = 600049  # The location is inactive
RECEIPT_DELETE_DRAFT_ONLY: Final = (
    600050  # Only draft receipts can be deleted (cancel instead)
)
RECEIPT_LINES_DRAFT_ONLY: Final = (
    600051  # Lines can only change while the receipt is a draft
)
RECEIPT_LINE_MOVE: Final = 600052  # A line cannot be moved to another receipt
RECEIPT_LINES_REQUIRED: Final = 600053  # Add at least one lot
RECEIPT_TRANSITION: Final = 600054  # The action "mes.receipt.action.{action})" is not allowed for a mes.enum.receipt_
RECEIPT_CONCURRENT: Final = 600055  # Another change happened at the same time; retry
ISSUE_EDIT_DRAFT_ONLY: Final = (
    600056  # Only draft material issues can be changed or deleted
)
ISSUE_WO_STATUS: Final = 600057  # Work order {wo} is {status}; cannot issue materials
ISSUE_QTY_EXCEEDS: Final = 600058  # Material lot {lot} has only {room} left
ISSUE_LINES_REQUIRED: Final = 600059  # Add at least one line
ISSUE_TRANSITION: Final = 600060  # A document that is {status} cannot do this
SHIP_QTY_EXCEEDS: Final = 600061  # Lot {lot} has only {room} left to ship
IQC_NOT_READY: Final = 600062  # Confirm the receipt before judging IQC
IQC_DECIDED: Final = 600063  # This line already has an IQC result

# ==================== MES 执行（作业、Hold、批量、载具、追溯、交接班） 700000-709999 ====================

ADJUST_KIND: Final = 700001  # The kind must be scrap or bonus
REASON_REQUIRED: Final = 700002  # reason required
COMMENT_REQUIRED: Final = 700003  # comment required
BONUS_QUANTITY_ONLY: Final = 700004  # Bonus is only for quantity-tracked lots
ADJUST_UNITS: Final = 700005  # Select active units of this lot
ADJUST_QTY_EXCEEDS: Final = 700006  # The qty exceeds the lot qty {qty}
BATCH_SIZE: Final = 700007  # batch size
BATCH_NOT_READY: Final = 700008  # batch not ready
BATCH_ROLLED_BACK: Final = 700009  # batch rolled back
BATCH_BLOCKED: Final = 700010  # batch blocked
BATCH_QTIME: Final = 700011  # batch qtime
CARRIER_CHANGE_STATUS: Final = 700012  # carrier change status
CARRIER_SAME: Final = 700013  # carrier same
CARRIER_UNAVAILABLE: Final = 700014  # carrier unavailable
CARRIER_CAPACITY: Final = 700015  # carrier capacity
CARRIER_BUSY: Final = 700016  # carrier busy
CARRIER_RETIRED: Final = 700017  # carrier retired
SORT_STATUS: Final = 700018  # sort status
CARRIER_REQUIRED: Final = 700019  # carrier required
SORT_SLOTS_ALL: Final = 700020  # sort slots all
SORT_SLOTS_UNIQUE: Final = 700021  # sort slots unique
CHECK_BLOCKED: Final = 700022  # check blocked
NO_CURRENT_STEP: Final = 700023  # no current step
EQUIPMENT_NOT_FOUND_2: Final = 700024  # equipment not found
FH_NOT_EDITABLE: Final = 700025  # fh not editable
LOT_TERMINAL: Final = 700026  # lot terminal
FH_STEP_NOT_ON_ROUTE: Final = 700027  # fh step not on route
REASON_MISSING: Final = 700028  # reason missing
HOLD_RELEASED: Final = 700029  # hold released
HOLD_NOT_FOUND: Final = 700030  # hold not found
MERGE_PICK: Final = 700031  # merge pick
MERGE_SOURCE_INVALID: Final = 700032  # merge source invalid
MERGE_LOT_NOT_FOUND: Final = 700033  # merge lot not found
PRIORITY_NOT_FOUND: Final = 700034  # priority not found
PRIORITY_UNCHANGED: Final = 700035  # priority unchanged
QTIME_RULE_IN_USE: Final = 700036  # qtime rule in use
JUMP_STATUS: Final = 700037  # jump status
JUMP_STEP_ROUTE: Final = 700038  # jump step route
JUMP_SAME_STEP: Final = 700039  # jump same step
JUMP_STEP_OPERATION: Final = 700040  # jump step operation
DATE_RANGE_INVERTED: Final = 700041  # date_from after date_to
DATE_RANGE_TOO_LONG_366: Final = 700042  # range too long (max 366 days)
DATE_RANGE_TOO_LONG_92: Final = 700043  # range too long (max 92 days)
SHIFT_NOT_FOUND: Final = 700044  # shift not found
AREA_NOT_FOUND: Final = 700045  # area not found
SUMMARY_REQUIRED: Final = 700046  # summary required
SHIFT_LOG_NOT_FOUND: Final = 700047  # shift log not found
ALREADY_ACKNOWLEDGED: Final = 700048  # already acknowledged
ACK_OTHER_USER: Final = 700049  # ack other user
CARRIER_NOT_FOUND: Final = 700050  # carrier not found
LOT_ID_RULE_MISSING: Final = 700051  # lot id rule missing
SPLIT_CHILDREN: Final = 700052  # split children
SPLIT_CHILD_QTY: Final = 700053  # split child qty
SPLIT_CHILD_UNITS: Final = 700054  # split child units
SPLIT_CHILD_UNITS_INVALID: Final = 700055  # split child units invalid
EQUIPMENT_NOT_MAIN: Final = 700056  # equipment not main
EQUIPMENT_REQUIRED: Final = 700057  # equipment required
CHAMBER_NOT_OF_EQUIPMENT: Final = 700058  # chamber not of equipment
CHAMBER_INACTIVE: Final = 700059  # chamber inactive
RECIPE_REQUIRED: Final = 700060  # recipe required
TOOL_REQUIRED: Final = 700061  # tool required
TRACE_KIND_INVALID: Final = 700062  # The trace kind must be one of: {allowed}
TRACE_NOT_FOUND: Final = 700063  # mes.traceq.k.{kind}) {code} not found
LOT_NOT_FOUND: Final = 700064  # lot not found
SCRAP_REASON_REQUIRED: Final = 700065  # Scrap {i}: a scrap reason code is required
SCRAP_QTY_MIN: Final = 700066  # Scrap {i}: qty must be at least 1
SCRAP_UNIT_NOT_IN_LOT: Final = 700067  # Scrap {i}: the unit is not in this lot
SCRAP_TOTAL_EXCEEDS: Final = 700068  # The scrap total exceeds the lot qty {qty}
SCRAP_UNIT_TWICE: Final = 700069  # A unit is listed twice in the scrap list
REWORK_UNIT_REQUIRED: Final = (
    700070  # Rework {i}: pick a unit of this lot and a rework reason
)
DC_ITEM_NOT_IN_PLAN: Final = (
    700071  # DC {i}: the measurement item is not in the DC plan
)
DC_VALUE_NUMBER: Final = 700072  # DC {i}: the value must be a number
DC_UNIT_NOT_IN_LOT: Final = 700073  # DC {i}: the unit is not in this lot
MATERIAL_INSUFFICIENT: Final = 700074  # Not enough material lots: {items}
CHECK_TYPE_NOT_IMPLEMENTED: Final = 700075  # This check type is not implemented
MUST_BE_JSON_OBJECT: Final = 700076  # Must be a JSON object
CONVERT_KIND: Final = 700077  # Target unit kind must be die, strip, package or unit
CONVERT_QUANTITY_LOT: Final = 700078  # A quantity-tracked lot has no units to convert
CONVERT_RATIO: Final = 700079  # Use either units per source or sources per unit
CONVERT_NO_UNITS: Final = 700080  # Select active units of this lot
CONVERT_NO_MAP: Final = 700081  # Wafer {unit} has no current die map
CONVERT_NO_GOOD_DIE: Final = 700082  # The die maps have no good die
CONVERT_TOO_MANY: Final = 700083  # {count} output units exceed the limit {max}
CONVERT_CODES_EXIST: Final = 700084  # Generated unit IDs already exist: {codes}
DIE_MAP_UNIT: Final = 700085  # Map {i}: the wafer is not in this lot
DIE_MAP_DIES: Final = 700086  # Map {i}: dies must be [x, y, bin] entries
DIE_MAP_DUPLICATE: Final = 700087  # Map {i}: die ({x}, {y}) appears twice
DIE_MAP_BINS: Final = 700088  # Unknown or inactive bin codes: {bins}
DIE_MAP_TOO_LARGE: Final = 700089  # Map {i}: at most {max} dies
BANK_NOT_FOUND: Final = 700090  # Bank not found or inactive
BANK_SOURCES: Final = 700091  # Pick at least one banked lot
BANK_MIXED_TRACKING: Final = 700092  # Source lots must have the same tracking level
BANK_UNITS: Final = 700093  # Source {lot}: units are not in the lot
BANK_QTY: Final = 700094  # Source {lot}: qty must be 1..{max}
NCR_STATUS: Final = 700095  # NCR {ncr} is {status}
NCR_SCRAP_REASON: Final = 700096  # Scrap disposition needs a scrap reason code
NCR_NO_REWORK_ROUTE: Final = 700097  # The current step has no rework route
NCR_SELF_APPROVE: Final = 700098  # The proposer cannot approve their own disposition
NCR_ALREADY_APPROVED: Final = 700099  # You already approved this disposition
NCR_REJECT_COMMENT: Final = 700100  # A comment is required to reject
NCR_UNITS: Final = 700101  # Affected units must belong to the lot

#: 错误码 -> 常量名（导出前端清单与测试用）
CODES: Final[dict[int, str]] = {
    v: k for k, v in list(globals().items()) if k.isupper() and isinstance(v, int)
}

#: Pydantic 错误类型 -> 错误码（未列出的类型用 ``PYD_INVALID``）
PYDANTIC_CODES: Final[dict[str, int]] = {
    "missing": PYD_MISSING,
    "extra_forbidden": PYD_EXTRA_FORBIDDEN,
    "string_type": PYD_STRING_TYPE,
    "int_type": PYD_INT_TYPE,
    "int_parsing": PYD_INT_PARSING,
    "int_from_float": PYD_INT_FROM_FLOAT,
    "float_type": PYD_FLOAT_TYPE,
    "float_parsing": PYD_FLOAT_PARSING,
    "decimal_type": PYD_DECIMAL_TYPE,
    "decimal_parsing": PYD_DECIMAL_PARSING,
    "bool_type": PYD_BOOL_TYPE,
    "bool_parsing": PYD_BOOL_PARSING,
    "uuid_type": PYD_UUID_TYPE,
    "uuid_parsing": PYD_UUID_PARSING,
    "date_type": PYD_DATE_TYPE,
    "date_parsing": PYD_DATE_PARSING,
    "date_from_datetime_parsing": PYD_DATE_FROM_DATETIME_PARSING,
    "datetime_type": PYD_DATETIME_TYPE,
    "datetime_parsing": PYD_DATETIME_PARSING,
    "time_type": PYD_TIME_TYPE,
    "time_parsing": PYD_TIME_PARSING,
    "string_too_short": PYD_STRING_TOO_SHORT,
    "string_too_long": PYD_STRING_TOO_LONG,
    "string_pattern_mismatch": PYD_STRING_PATTERN_MISMATCH,
    "greater_than": PYD_GREATER_THAN,
    "greater_than_equal": PYD_GREATER_THAN_EQUAL,
    "less_than": PYD_LESS_THAN,
    "less_than_equal": PYD_LESS_THAN_EQUAL,
    "too_short": PYD_TOO_SHORT,
    "too_long": PYD_TOO_LONG,
    "literal_error": PYD_LITERAL_ERROR,
    "enum": PYD_ENUM,
    "json_invalid": PYD_JSON_INVALID,
    "dict_type": PYD_DICT_TYPE,
    "model_attributes_type": PYD_MODEL_ATTRIBUTES_TYPE,
    "model_type": PYD_MODEL_TYPE,
    "list_type": PYD_LIST_TYPE,
    "url_parsing": PYD_URL_PARSING,
    "url_type": PYD_URL_TYPE,
    "value_error": PYD_VALUE_ERROR,
    "assertion_error": PYD_ASSERTION_ERROR,
}
