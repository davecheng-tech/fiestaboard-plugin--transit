"""Tests for the transit plugin."""

import json
import shutil
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from plugins.transit import TransitPlugin, Plugin


MANIFEST_PATH = Path(__file__).resolve().parent.parent / "manifest.json"


@pytest.fixture
def plugin():
    manifest = {"id": "transit", "name": "Transit", "version": "1.0.0"}
    return TransitPlugin(manifest)


class TestPluginIdentity:
    """Plugin registers under its own id, separate from the traffic plugin."""

    def test_plugin_id(self, plugin):
        assert plugin.plugin_id == "transit"

    def test_export_is_transit_plugin(self):
        assert Plugin is TransitPlugin

    def test_manifest_id_matches_plugin_id(self, plugin):
        with open(MANIFEST_PATH) as f:
            manifest = json.load(f)
        assert manifest["id"] == plugin.plugin_id


class TestValidateConfig:
    """Config validation is unchanged from the traffic plugin."""

    def test_valid(self, plugin):
        config = {"api_key": "k", "routes": [{"origin": "A", "destination": "B"}]}
        assert plugin.validate_config(config) == []

    def test_missing_key(self, plugin):
        errors = plugin.validate_config({"routes": [{}]})
        assert any("API key" in e for e in errors)

    def test_missing_routes(self, plugin):
        errors = plugin.validate_config({"api_key": "k"})
        assert any("route" in e for e in errors)

    def test_empty(self, plugin):
        assert len(plugin.validate_config({})) == 2


class TestDurationParsing:
    def test_parse_duration(self, plugin):
        assert plugin._parse_duration("1800s") == 1800
        assert plugin._parse_duration("") == 0
        assert plugin._parse_duration("3600") == 3600


class TestBuildWaypoint:
    """Waypoint resolution is not travel-mode specific."""

    def test_address(self, plugin):
        assert plugin._build_waypoint("123 Main St, City, ST") == {
            "address": "123 Main St, City, ST"
        }

    def test_latlng(self, plugin):
        wp = plugin._build_waypoint("43.6452, -79.3806")
        assert wp["location"]["latLng"]["latitude"] == 43.6452
        assert wp["location"]["latLng"]["longitude"] == -79.3806

    def test_latlng_no_space(self, plugin):
        wp = plugin._build_waypoint("43.6452,-79.3806")
        assert wp["location"]["latLng"]["latitude"] == 43.6452

    def test_invalid_latlng_falls_back_to_address(self, plugin):
        assert plugin._build_waypoint("abc, def") == {"address": "abc, def"}


def _mock_response(payload, status_code=200):
    resp = Mock()
    resp.status_code = status_code
    resp.text = json.dumps(payload)
    resp.json.return_value = payload
    return resp


class TestFetchSingleRoute:
    def test_request_uses_transit_mode(self, plugin):
        """travelMode is TRANSIT and routingPreference is absent.

        routingPreference is DRIVE-only; sending it with TRANSIT makes the
        Routes API reject the request.
        """
        plugin._config = {"api_key": "test_key"}
        resp = _mock_response({"routes": [{"duration": "1920s"}]})

        with patch("plugins.transit.requests.post", return_value=resp) as post:
            plugin._fetch_single_route("Home", "Union Station", "UNION")

        body = post.call_args.kwargs["json"]
        assert body["travelMode"] == "TRANSIT"
        assert "routingPreference" not in body
        assert body["origin"] == {"address": "Home"}
        assert body["destination"] == {"address": "Union Station"}

    def test_field_mask_requests_duration_only(self, plugin):
        """staticDuration does not exist on transit responses."""
        plugin._config = {"api_key": "test_key"}
        resp = _mock_response({"routes": [{"duration": "1920s"}]})

        with patch("plugins.transit.requests.post", return_value=resp) as post:
            plugin._fetch_single_route("Home", "Work", "WORK")

        assert post.call_args.kwargs["headers"]["X-Goog-FieldMask"] == "routes.duration"
        assert post.call_args.kwargs["headers"]["X-Goog-Api-Key"] == "test_key"

    def test_success_shape(self, plugin):
        plugin._config = {"api_key": "test_key"}
        resp = _mock_response({"routes": [{"duration": "1920s"}]})

        with patch("plugins.transit.requests.post", return_value=resp):
            result = plugin._fetch_single_route("Home", "Work", "WORK")

        assert result == {
            "duration_minutes": 32,
            "destination_name": "WORK",
            "formatted": "WORK: 32m",
        }

    def test_duration_is_rounded_to_nearest_minute(self, plugin):
        plugin._config = {"api_key": "test_key"}
        resp = _mock_response({"routes": [{"duration": "1970s"}]})

        with patch("plugins.transit.requests.post", return_value=resp):
            result = plugin._fetch_single_route("Home", "Work", "WORK")

        assert result["duration_minutes"] == 33

    def test_half_minute_rounds_to_even(self, plugin):
        """round() is banker's rounding; 32.5 min -> 32, same as the traffic plugin."""
        plugin._config = {"api_key": "test_key"}
        resp = _mock_response({"routes": [{"duration": "1950s"}]})

        with patch("plugins.transit.requests.post", return_value=resp):
            result = plugin._fetch_single_route("Home", "Work", "WORK")

        assert result["duration_minutes"] == 32

    def test_missing_duration_defaults_to_zero(self, plugin):
        plugin._config = {"api_key": "test_key"}
        resp = _mock_response({"routes": [{}]})

        with patch("plugins.transit.requests.post", return_value=resp):
            result = plugin._fetch_single_route("Home", "Work", "WORK")

        assert result["duration_minutes"] == 0

    def test_bad_status_returns_none(self, plugin):
        plugin._config = {"api_key": "test_key"}
        resp = _mock_response({"error": {"message": "bad request"}}, status_code=400)

        with patch("plugins.transit.requests.post", return_value=resp):
            assert plugin._fetch_single_route("Home", "Work", "WORK") is None

    def test_bad_status_logs_response_body(self, plugin, caplog):
        """A rejected transit request must surface Google's reason in the log."""
        plugin._config = {"api_key": "test_key"}
        resp = _mock_response(
            {"error": {"message": "routingPreference is not supported"}},
            status_code=400,
        )

        with patch("plugins.transit.requests.post", return_value=resp):
            with caplog.at_level("ERROR"):
                plugin._fetch_single_route("Home", "Work", "WORK")

        assert "routingPreference is not supported" in caplog.text

    def test_empty_routes_returns_none(self, plugin):
        """No transit service between the two points."""
        plugin._config = {"api_key": "test_key"}
        resp = _mock_response({})

        with patch("plugins.transit.requests.post", return_value=resp):
            assert plugin._fetch_single_route("Home", "Work", "WORK") is None

    def test_request_exception_returns_none(self, plugin):
        plugin._config = {"api_key": "test_key"}

        with patch("plugins.transit.requests.post", side_effect=Exception("boom")):
            assert plugin._fetch_single_route("Home", "Work", "WORK") is None


class TestFetchData:
    def test_no_routes_configured(self, plugin):
        plugin._config = {}
        result = plugin.fetch_data()
        assert not result.available
        assert result.error == "No routes configured"

    def test_all_routes_fail(self, plugin):
        plugin._config = {
            "api_key": "k",
            "routes": [{"origin": "A", "destination": "B", "destination_name": "X"}],
        }
        with patch("plugins.transit.requests.post", side_effect=Exception("boom")):
            result = plugin.fetch_data()
        assert not result.available
        assert result.error == "Failed to fetch any route data"

    def test_success_aggregates(self, plugin):
        plugin._config = {
            "api_key": "k",
            "routes": [
                {"origin": "A", "destination": "B", "destination_name": "UNION"},
                {"origin": "A", "destination": "C", "destination_name": "AIRPORT"},
            ],
        }
        responses = [
            _mock_response({"routes": [{"duration": "1920s"}]}),
            _mock_response({"routes": [{"duration": "2820s"}]}),
        ]
        with patch("plugins.transit.requests.post", side_effect=responses):
            result = plugin.fetch_data()

        assert result.available
        data = result.data
        assert data["duration_minutes"] == 32
        assert data["destination_name"] == "UNION"
        assert data["formatted"] == "UNION: 32m"
        assert data["route_count"] == 2
        assert data["longest_duration"] == 47
        assert len(data["routes"]) == 2
        assert data["routes"][1]["destination_name"] == "AIRPORT"

    def test_no_traffic_fields_in_output(self, plugin):
        """Traffic-index fields have no transit equivalent and must be gone."""
        plugin._config = {
            "api_key": "k",
            "routes": [{"origin": "A", "destination": "B", "destination_name": "X"}],
        }
        resp = _mock_response({"routes": [{"duration": "1920s"}]})
        with patch("plugins.transit.requests.post", return_value=resp):
            result = plugin.fetch_data()

        dropped = {"delay_minutes", "traffic_status", "traffic_color", "worst_delay"}
        assert not dropped & set(result.data)
        assert not dropped & set(result.data["routes"][0])

    def test_caps_at_four_routes(self, plugin):
        plugin._config = {
            "api_key": "k",
            "routes": [
                {"origin": "A", "destination": str(i), "destination_name": f"D{i}"}
                for i in range(6)
            ],
        }
        resp = _mock_response({"routes": [{"duration": "600s"}]})
        with patch("plugins.transit.requests.post", return_value=resp) as post:
            result = plugin.fetch_data()

        assert post.call_count == 4
        assert result.data["route_count"] == 4

    def test_partial_failure_keeps_good_routes(self, plugin):
        plugin._config = {
            "api_key": "k",
            "routes": [
                {"origin": "A", "destination": "B", "destination_name": "GOOD"},
                {"origin": "A", "destination": "C", "destination_name": "BAD"},
            ],
        }
        responses = [
            _mock_response({"routes": [{"duration": "600s"}]}),
            _mock_response({}, status_code=400),
        ]
        with patch("plugins.transit.requests.post", side_effect=responses):
            result = plugin.fetch_data()

        assert result.available
        assert result.data["route_count"] == 1
        assert result.data["destination_name"] == "GOOD"

    def test_missing_destination_name_defaults(self, plugin):
        plugin._config = {"api_key": "k", "routes": [{"origin": "A", "destination": "B"}]}
        resp = _mock_response({"routes": [{"duration": "600s"}]})
        with patch("plugins.transit.requests.post", return_value=resp):
            result = plugin.fetch_data()

        assert result.data["destination_name"] == "DEST"


class TestFormattedDisplay:
    def test_uses_cache(self, plugin):
        plugin._cache = {
            "routes": [
                {"formatted": "UNION: 32m"},
                {"formatted": "AIRPORT: 47m"},
            ]
        }
        lines = plugin.get_formatted_display()
        assert len(lines) == 6
        assert lines[0].strip() == "TRANSIT"
        assert lines[2] == "UNION: 32m"
        assert lines[3] == "AIRPORT: 47m"

    def test_truncates_to_board_width(self, plugin):
        plugin._cache = {"routes": [{"formatted": "X" * 40}]}
        lines = plugin.get_formatted_display()
        assert all(len(line) <= 22 for line in lines)

    def test_fetches_when_cache_empty(self, plugin):
        plugin._config = {
            "api_key": "k",
            "routes": [{"origin": "A", "destination": "B", "destination_name": "UNION"}],
        }
        resp = _mock_response({"routes": [{"duration": "1920s"}]})
        with patch("plugins.transit.requests.post", return_value=resp):
            lines = plugin.get_formatted_display()

        assert lines[2] == "UNION: 32m"

    def test_returns_none_when_fetch_fails(self, plugin):
        plugin._config = {}
        assert plugin.get_formatted_display() is None


class TestManifestMetadata:
    """Tests for rich variable metadata in manifest.json."""

    @pytest.fixture(autouse=True)
    def load_manifest(self):
        with open(MANIFEST_PATH) as f:
            self.manifest = json.load(f)
        self.variables = self.manifest["variables"]

    def test_required_top_level_fields(self):
        for field in ("id", "name", "version", "variables"):
            assert field in self.manifest, f"Missing required field: {field}"

    def test_simple_variables_are_dicts(self):
        assert isinstance(self.variables["simple"], dict)

    def test_simple_variable_required_keys(self):
        required = {"description", "type", "max_length", "group", "example"}
        for var_name, meta in self.variables["simple"].items():
            missing = required - set(meta.keys())
            assert not missing, f"{var_name} missing keys: {missing}"

    def test_groups_defined(self):
        assert "groups" in self.variables
        assert len(self.variables["groups"]) > 0

    def test_simple_variables_reference_valid_groups(self):
        groups = set(self.variables["groups"].keys())
        for var_name, meta in self.variables["simple"].items():
            assert meta["group"] in groups, (
                f"{var_name} references unknown group '{meta['group']}'"
            )

    def test_array_item_fields_reference_simple_vars(self):
        simple_keys = set(self.variables["simple"].keys())
        for arr_name, arr_meta in self.variables.get("arrays", {}).items():
            for field in arr_meta.get("item_fields", []):
                assert field in simple_keys, (
                    f"arrays.{arr_name} references unknown field '{field}'"
                )

    def test_variable_types_valid(self):
        valid_types = {"string", "number", "boolean"}
        for var_name, meta in self.variables["simple"].items():
            assert meta["type"] in valid_types, (
                f"{var_name} has invalid type '{meta['type']}'"
            )

    def test_max_length_positive(self):
        for var_name, meta in self.variables["simple"].items():
            assert meta["max_length"] > 0

    def test_example_values_present(self):
        for var_name, meta in self.variables["simple"].items():
            assert meta["example"], f"{var_name} must have a non-empty example"

    def test_no_traffic_variables_remain(self):
        """Traffic-index variables were dropped, not adapted."""
        dropped = {"delay_minutes", "traffic_status", "traffic_color", "worst_delay"}
        assert not dropped & set(self.variables["simple"])

    def test_declared_variables_match_plugin_output(self, plugin):
        """Every simple variable in the manifest is produced by fetch_data()."""
        plugin._config = {
            "api_key": "k",
            "routes": [{"origin": "A", "destination": "B", "destination_name": "X"}],
        }
        resp = _mock_response({"routes": [{"duration": "600s"}]})
        with patch("plugins.transit.requests.post", return_value=resp):
            result = plugin.fetch_data()

        declared = set(self.variables["simple"])
        assert declared <= set(result.data), declared - set(result.data)

        item_fields = set(self.variables["arrays"]["routes"]["item_fields"])
        assert item_fields == set(result.data["routes"][0])

    def test_category_is_transit(self):
        assert self.manifest["category"] == "transit"


class TestCoreManifestValidation:
    """Validate manifest.json with FiestaBoard core's own loader.

    The hand-rolled metadata checks above passed on a manifest that core
    rejected outright (a 16-tile teaser against a 15-tile limit), which kept
    the plugin off the Integrations page entirely. Anything core treats as a
    hard error must fail here instead.
    """

    def test_manifest_loads_without_errors(self):
        from src.plugins.manifest import load_manifest

        manifest, errors = load_manifest(MANIFEST_PATH)
        assert errors == [], f"core rejected manifest.json: {errors}"
        assert manifest is not None

    def test_manifest_id_matches_directory_name(self):
        """The loader refuses a plugin whose manifest id != its directory."""
        from src.plugins.manifest import load_manifest

        manifest, _ = load_manifest(MANIFEST_PATH)
        assert manifest.id == "transit"

    def test_plugin_loads_through_core_loader(self, tmp_path):
        """End-to-end: core discovers, validates, and imports this plugin."""
        from src.plugins.loader import PluginLoader

        # A real copy, not a symlink: the loader resolves the plugin dir and
        # rejects anything that escapes the external dir (loader.py's
        # containment barrier), so a symlinked plugin never loads.
        repo_root = MANIFEST_PATH.parent
        ext_dir = tmp_path / "external_plugins"
        ext_dir.mkdir()
        shutil.copytree(
            repo_root,
            ext_dir / "transit",
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"),
        )

        loader = PluginLoader(plugins_dir=tmp_path / "builtin", external_dirs=[ext_dir])
        loaded = loader.load_all_plugins()

        assert loader.load_errors == {}
        assert "transit" in loaded
        assert loaded["transit"].plugin_id == "transit"
