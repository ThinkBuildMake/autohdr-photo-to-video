"""Shared value sets (ARCHITECTURE: Shared types). More values may be added."""

from enum import StrEnum


class JobStatus(StrEnum):
    draft = "draft"
    queued = "queued"
    running = "running"
    ready = "ready"
    ready_with_failures = "ready_with_failures"
    stopped = "stopped"


class ShotStatus(StrEnum):
    pending = "pending"
    editing = "editing"
    generating = "generating"
    checking = "checking"
    passed = "passed"
    failed = "failed"
    skipped = "skipped"


class StopReason(StrEnum):
    out_of_credit = "out_of_credit"
    worker_restarted = "worker_restarted"
    assembly_failed = "assembly_failed"
    no_shot_passed = "no_shot_passed"


class FailureReason(StrEnum):
    flagged_every_attempt = "flagged_every_attempt"
    provider_error = "provider_error"
    refused = "refused"
    out_of_time = "out_of_time"
    no_photo = "no_photo"
    job_stopped = "job_stopped"


class ProviderErrorKind(StrEnum):
    rate_limited = "rate_limited"
    out_of_credit = "out_of_credit"
    refused = "refused"
    failed = "failed"
    timeout = "timeout"
    bad_response = "bad_response"


class Room(StrEnum):
    exterior_front = "exterior_front"
    exterior_back = "exterior_back"
    living = "living"
    kitchen = "kitchen"
    dining = "dining"
    bedroom = "bedroom"
    bathroom = "bathroom"
    office = "office"
    hallway = "hallway"
    detail = "detail"
    aerial = "aerial"
    other = "other"


class MovementName(StrEnum):
    dolly_in = "dolly_in"
    dolly_in_timelapse = "dolly_in_timelapse"
    drone_top_down_descend = "drone_top_down_descend"
    timelapse_variant = "timelapse_variant"
    dolly_out = "dolly_out"
    slider_truck_left_to_right = "slider_truck_left_to_right"
    slider_truck_right_to_left = "slider_truck_right_to_left"
    parallax_orbit = "parallax_orbit"
    dolly_in_pan_right = "dolly_in_pan_right"
    crane_up = "crane_up"
    crane_down = "crane_down"
    orbit_hyperlapse = "orbit_hyperlapse"
