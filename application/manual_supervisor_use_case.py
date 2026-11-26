"""Application supervisor loop for an existing Manual session."""

import asyncio


async def supervise_manual_session(session, *, poll_seconds):
    self = session
    try:
        while self.is_active:
            await self.observe_once()
            if not self.is_active:
                break
            await asyncio.sleep(poll_seconds)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        self.stop_reason = f"manual_runtime_error:{type(exc).__name__}"
        try:
            try:
                await self.execution_port.request_emergency_off()
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        finally:
            self._transition_state(type(self.state).FAILED, self.stop_reason)
            self._persist()
