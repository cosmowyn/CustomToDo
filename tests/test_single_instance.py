from __future__ import annotations

import uuid

import main as main_module


def test_single_instance_guard_redirects_later_launches_to_existing_instance(qapp):
    server_name = f"gridoryn-test-{uuid.uuid4().hex}"
    activations: list[str] = []

    first_name, first_server, first_running = main_module._acquire_single_instance_guard(
        lambda: activations.append("activate"),
        server_name=server_name,
    )
    assert first_name == server_name
    assert first_running is False
    assert first_server is not None

    try:
        second_name, second_server, second_running = main_module._acquire_single_instance_guard(
            lambda: activations.append("unexpected"),
            server_name=server_name,
        )
        assert second_name == server_name
        assert second_running is True
        assert second_server is None

        qapp.processEvents()
        qapp.processEvents()

        assert activations == ["activate"]
    finally:
        main_module._release_single_instance_guard(server_name, first_server)
