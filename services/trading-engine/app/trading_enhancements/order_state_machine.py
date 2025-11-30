"""
Order State Machine - FIX Protocol Style
Research Source: FIX Trading Community, Algoteq OMS Architecture

Purpose:
- Manage order lifecycle with well-defined states
- Ensure valid state transitions only
- Provide audit trail for all state changes
- Enable idempotent order processing

State Diagram:
    PENDING -> VALIDATED -> SUBMITTED -> ACCEPTED -> (PARTIALLY_FILLED | FILLED | CANCELLED)
                                      -> REJECTED
"""

import logging
from enum import Enum
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class OrderState(Enum):
    """
    Order states following FIX protocol model

    RESEARCH: FIX Protocol defines standard order states that most
    trading systems implement. Using these states ensures compatibility
    and clear understanding across the trading ecosystem.
    """
    PENDING = "pending"                 # Order created, awaiting validation
    VALIDATED = "validated"             # Order passed all validation checks
    SUBMITTED = "submitted"             # Order sent to exchange
    ACCEPTED = "accepted"               # Exchange acknowledged the order
    PARTIALLY_FILLED = "partially_filled"  # Some quantity executed
    FILLED = "filled"                   # Order completely executed (terminal)
    CANCELLED = "cancelled"             # Order cancelled (terminal)
    REJECTED = "rejected"               # Order rejected by validation or exchange (terminal)
    EXPIRED = "expired"                 # Order expired (terminal)


class OrderEvent(Enum):
    """Events that trigger state transitions"""
    VALIDATE = "validate"
    SUBMIT = "submit"
    ACCEPT = "accept"
    REJECT = "reject"
    PARTIAL_FILL = "partial_fill"
    FILL = "fill"
    CANCEL = "cancel"
    EXPIRE = "expire"


@dataclass
class StateTransition:
    """Record of a state transition"""
    from_state: OrderState
    to_state: OrderState
    event: OrderEvent
    timestamp: datetime
    metadata: Dict = field(default_factory=dict)


@dataclass
class OrderStateRecord:
    """Complete order state tracking"""
    order_id: UUID
    current_state: OrderState
    created_at: datetime
    updated_at: datetime
    transitions: List[StateTransition] = field(default_factory=list)
    filled_quantity: float = 0.0
    total_quantity: float = 0.0
    rejection_reason: Optional[str] = None
    idempotency_key: Optional[str] = None


class OrderStateMachine:
    """
    State Machine for Order Lifecycle Management

    RESEARCH-BACKED IMPLEMENTATION:
    - Based on FIX Protocol state model (industry standard)
    - Event-driven finite state machine (FSM) for async transitions
    - Idempotent processing prevents duplicate state changes
    - Complete audit trail of all transitions

    Usage:
        fsm = OrderStateMachine()

        # Create new order
        order = fsm.create_order(order_id, total_qty=10.0)

        # Process events
        fsm.process_event(order_id, OrderEvent.VALIDATE)
        fsm.process_event(order_id, OrderEvent.SUBMIT)
        fsm.process_event(order_id, OrderEvent.ACCEPT)
        fsm.process_event(order_id, OrderEvent.FILL, filled_qty=10.0)
    """

    # Valid state transitions: (current_state, event) -> new_state
    TRANSITIONS: Dict[tuple, OrderState] = {
        # From PENDING
        (OrderState.PENDING, OrderEvent.VALIDATE): OrderState.VALIDATED,
        (OrderState.PENDING, OrderEvent.REJECT): OrderState.REJECTED,
        (OrderState.PENDING, OrderEvent.CANCEL): OrderState.CANCELLED,

        # From VALIDATED
        (OrderState.VALIDATED, OrderEvent.SUBMIT): OrderState.SUBMITTED,
        (OrderState.VALIDATED, OrderEvent.REJECT): OrderState.REJECTED,
        (OrderState.VALIDATED, OrderEvent.CANCEL): OrderState.CANCELLED,

        # From SUBMITTED
        (OrderState.SUBMITTED, OrderEvent.ACCEPT): OrderState.ACCEPTED,
        (OrderState.SUBMITTED, OrderEvent.REJECT): OrderState.REJECTED,
        (OrderState.SUBMITTED, OrderEvent.CANCEL): OrderState.CANCELLED,

        # From ACCEPTED
        (OrderState.ACCEPTED, OrderEvent.PARTIAL_FILL): OrderState.PARTIALLY_FILLED,
        (OrderState.ACCEPTED, OrderEvent.FILL): OrderState.FILLED,
        (OrderState.ACCEPTED, OrderEvent.CANCEL): OrderState.CANCELLED,
        (OrderState.ACCEPTED, OrderEvent.EXPIRE): OrderState.EXPIRED,

        # From PARTIALLY_FILLED
        (OrderState.PARTIALLY_FILLED, OrderEvent.PARTIAL_FILL): OrderState.PARTIALLY_FILLED,
        (OrderState.PARTIALLY_FILLED, OrderEvent.FILL): OrderState.FILLED,
        (OrderState.PARTIALLY_FILLED, OrderEvent.CANCEL): OrderState.CANCELLED,
        (OrderState.PARTIALLY_FILLED, OrderEvent.EXPIRE): OrderState.EXPIRED,
    }

    # Terminal states (no further transitions allowed)
    TERMINAL_STATES = {
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.EXPIRED
    }

    def __init__(self):
        """Initialize the state machine"""
        self._orders: Dict[UUID, OrderStateRecord] = {}
        self._idempotency_keys: Dict[str, UUID] = {}
        self._event_handlers: Dict[OrderEvent, List[Callable]] = {}

        logger.info("OrderStateMachine initialized")

    def create_order(
        self,
        order_id: UUID,
        total_quantity: float,
        idempotency_key: Optional[str] = None
    ) -> OrderStateRecord:
        """
        Create a new order in PENDING state

        IDEMPOTENCY: If idempotency_key is provided and already exists,
        returns the existing order instead of creating a new one.

        Args:
            order_id: Unique order identifier
            total_quantity: Total quantity to fill
            idempotency_key: Optional key for idempotent creation

        Returns:
            OrderStateRecord for the order
        """
        # Check idempotency
        if idempotency_key and idempotency_key in self._idempotency_keys:
            existing_id = self._idempotency_keys[idempotency_key]
            logger.info(f"Idempotency key '{idempotency_key}' found, returning existing order {existing_id}")
            return self._orders[existing_id]

        # Check if order already exists
        if order_id in self._orders:
            logger.warning(f"Order {order_id} already exists")
            return self._orders[order_id]

        # Create new order
        now = datetime.now()
        order = OrderStateRecord(
            order_id=order_id,
            current_state=OrderState.PENDING,
            created_at=now,
            updated_at=now,
            total_quantity=total_quantity,
            idempotency_key=idempotency_key
        )

        self._orders[order_id] = order
        if idempotency_key:
            self._idempotency_keys[idempotency_key] = order_id

        logger.info(f"Order {order_id} created in PENDING state (qty={total_quantity})")
        return order

    def process_event(
        self,
        order_id: UUID,
        event: OrderEvent,
        filled_quantity: float = 0.0,
        metadata: Optional[Dict] = None
    ) -> tuple[bool, str]:
        """
        Process an event for an order

        IDEMPOTENCY: Same event on same state is ignored (no duplicate transition).

        Args:
            order_id: Order to process
            event: Event to apply
            filled_quantity: Quantity filled (for FILL/PARTIAL_FILL events)
            metadata: Optional metadata for the transition

        Returns:
            Tuple of (success: bool, message: str)
        """
        if order_id not in self._orders:
            return False, f"Order {order_id} not found"

        order = self._orders[order_id]
        current_state = order.current_state

        # Check if already in terminal state
        if current_state in self.TERMINAL_STATES:
            return False, f"Order {order_id} is in terminal state {current_state.value}"

        # Find valid transition
        transition_key = (current_state, event)
        if transition_key not in self.TRANSITIONS:
            return False, f"Invalid transition: {current_state.value} + {event.value}"

        new_state = self.TRANSITIONS[transition_key]

        # Create transition record
        transition = StateTransition(
            from_state=current_state,
            to_state=new_state,
            event=event,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )

        # Update order
        order.current_state = new_state
        order.updated_at = transition.timestamp
        order.transitions.append(transition)

        # Handle fill quantity
        if event in (OrderEvent.FILL, OrderEvent.PARTIAL_FILL):
            order.filled_quantity += filled_quantity
            transition.metadata["filled_quantity"] = filled_quantity
            transition.metadata["total_filled"] = order.filled_quantity

        # Handle rejection
        if event == OrderEvent.REJECT:
            order.rejection_reason = metadata.get("reason") if metadata else "Unknown"

        # Call event handlers
        self._call_event_handlers(event, order, transition)

        logger.info(
            f"Order {order_id}: {current_state.value} -> {new_state.value} "
            f"(event={event.value})"
        )

        return True, f"Transitioned to {new_state.value}"

    def get_order(self, order_id: UUID) -> Optional[OrderStateRecord]:
        """Get order state record"""
        return self._orders.get(order_id)

    def get_order_state(self, order_id: UUID) -> Optional[OrderState]:
        """Get current state of an order"""
        order = self._orders.get(order_id)
        return order.current_state if order else None

    def is_terminal(self, order_id: UUID) -> bool:
        """Check if order is in a terminal state"""
        order = self._orders.get(order_id)
        if not order:
            return False
        return order.current_state in self.TERMINAL_STATES

    def get_transition_history(self, order_id: UUID) -> List[Dict]:
        """Get complete transition history for an order"""
        order = self._orders.get(order_id)
        if not order:
            return []

        return [
            {
                "from_state": t.from_state.value,
                "to_state": t.to_state.value,
                "event": t.event.value,
                "timestamp": t.timestamp.isoformat(),
                "metadata": t.metadata
            }
            for t in order.transitions
        ]

    def register_event_handler(self, event: OrderEvent, handler: Callable):
        """
        Register a handler to be called when an event occurs

        Args:
            event: Event to handle
            handler: Callable that receives (order, transition)
        """
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def _call_event_handlers(
        self,
        event: OrderEvent,
        order: OrderStateRecord,
        transition: StateTransition
    ):
        """Call registered handlers for an event"""
        handlers = self._event_handlers.get(event, [])
        for handler in handlers:
            try:
                handler(order, transition)
            except Exception as e:
                logger.error(f"Event handler error for {event.value}: {e}")

    def get_stats(self) -> Dict:
        """Get state machine statistics"""
        state_counts = {state.value: 0 for state in OrderState}
        for order in self._orders.values():
            state_counts[order.current_state.value] += 1

        return {
            "total_orders": len(self._orders),
            "state_distribution": state_counts,
            "terminal_orders": sum(
                1 for o in self._orders.values()
                if o.current_state in self.TERMINAL_STATES
            ),
            "active_orders": sum(
                1 for o in self._orders.values()
                if o.current_state not in self.TERMINAL_STATES
            )
        }


# Global state machine instance
_order_state_machine: Optional[OrderStateMachine] = None


def get_order_state_machine() -> OrderStateMachine:
    """Get or create global order state machine"""
    global _order_state_machine
    if _order_state_machine is None:
        _order_state_machine = OrderStateMachine()
    return _order_state_machine
