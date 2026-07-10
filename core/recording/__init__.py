"""core.recording — 三種錄音模式 + 麥克風裝置管理。"""
from core.recording.devices import (
    list_input_devices, resolve_input_device, test_input_device,
)
from core.recording.recorder import Recorder
from core.recording.streaming_recorder import StreamingRecorder
from core.recording.meeting_recorder import MeetingRecorder

__all__ = [
    'list_input_devices', 'resolve_input_device', 'test_input_device',
    'Recorder', 'StreamingRecorder', 'MeetingRecorder',
]
