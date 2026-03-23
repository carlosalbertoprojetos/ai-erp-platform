from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from secrets import token_hex
from typing import Any


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    traceparent: str


class TraceHandle(AbstractContextManager['TraceHandle']):
    def __init__(self, context: TraceContext, span: Any | None = None):
        self.context = context
        self._span = span

    def __enter__(self) -> 'TraceHandle':
        return self

    def __exit__(self, exc_type, exc, exc_tb) -> None:
        if self._span is None:
            return None
        if exc is not None and hasattr(self._span, 'record_exception'):
            self._span.record_exception(exc)
        if hasattr(self._span, 'end'):
            self._span.end()
        return None

    def set_attribute(self, key: str, value: Any) -> None:
        if self._span is not None and hasattr(self._span, 'set_attribute'):
            self._span.set_attribute(key, value)


class TracerAdapter:
    def __init__(self, service_name: str, enabled: bool = True):
        self.service_name = service_name
        self.enabled = enabled
        self._otel_trace = None
        self._tracer = None
        if enabled:
            self._initialize_opentelemetry()

    def _initialize_opentelemetry(self) -> None:
        try:
            from opentelemetry import trace as otel_trace
        except Exception:
            return
        self._otel_trace = otel_trace
        self._tracer = otel_trace.get_tracer(self.service_name)

    def start_span(self, name: str, incoming_traceparent: str | None = None) -> TraceHandle:
        trace_id = self._extract_trace_id(incoming_traceparent) or token_hex(16)
        span_id = token_hex(8)
        traceparent = f'00-{trace_id}-{span_id}-01'
        if self._tracer is None:
            return TraceHandle(TraceContext(trace_id=trace_id, span_id=span_id, traceparent=traceparent))
        span = self._tracer.start_span(name)
        context = TraceContext(trace_id=trace_id, span_id=span_id, traceparent=traceparent)
        if hasattr(span, 'set_attribute'):
            span.set_attribute('service.name', self.service_name)
            span.set_attribute('coreflow.traceparent', traceparent)
        return TraceHandle(context=context, span=span)

    def _extract_trace_id(self, traceparent: str | None) -> str | None:
        if not traceparent:
            return None
        parts = traceparent.split('-')
        if len(parts) != 4:
            return None
        trace_id = parts[1].strip().lower()
        if len(trace_id) != 32:
            return None
        return trace_id
