from datetime import date

from app.markdown.renderer import MarkdownRenderer
from app.schemas.internal import (
    ActivitySummary,
    HeartRateZone,
    NormalizedActivity,
    PhysiologySnapshot,
    Split,
    TimeSeriesPoint,
)


def build_activity() -> NormalizedActivity:
    return NormalizedActivity(
        summary=ActivitySummary(
            activity_id="123456789",
            date=date(2026, 4, 19),
            activity_type="running",
            title="Endurance fondamentale",
            distance_km=10.24,
            duration_seconds=3133,
            moving_duration_seconds=3100,
            average_pace_min_per_km=5.1,
            average_hr=148,
            max_hr=174,
            training_load=142,
            fitness_state="productive",
            training_effect_aerobic=3.2,
            training_effect_anaerobic=0.8,
            elevation_gain_m=86,
            elevation_loss_m=74,
            calories=640,
            vo2max=52,
            avg_power=256,
            max_power=612,
            avg_stride_length=1.18,
            avg_vertical_ratio=7.4,
            avg_vertical_oscillation=8.7,
            avg_ground_contact_time=241,
            start_stamina=91,
            end_stamina=43,
            min_stamina=39,
        ),
        physiology=PhysiologySnapshot(
            hrv_avg_ms=54,
            body_battery_start=72,
            body_battery_end=41,
            stress_avg=28,
            recovery_time_hours=18,
        ),
        splits=[
            Split(
                index=1,
                step_type="Échauffement",
                distance_km=0.4,
                duration_seconds=78,
                pace_min_per_km=3.25,
                average_hr=137,
                max_hr=149,
                elevation_gain_m=8,
                elevation_loss_m=2,
            ),
            Split(
                index=2,
                step_type="Récupération",
                distance_km=0.6,
                duration_seconds=230,
                pace_min_per_km=6.3888888889,
                average_hr=144,
                max_hr=153,
                elevation_gain_m=4,
                elevation_loss_m=1,
            ),
        ],
        heart_rate_zones=[
            HeartRateZone(zone="Z1", duration_seconds=120),
            HeartRateZone(zone="Z2", duration_seconds=900),
        ],
        time_series=[
            TimeSeriesPoint(
                elapsed_seconds=0,
                distance_km=0.01,
                heart_rate=131,
                pace_min_per_km=5.7471,
                elevation_m=120.5,
                cadence_spm=166,
                power_w=248,
            ),
            TimeSeriesPoint(
                elapsed_seconds=10,
                distance_km=0.04,
                heart_rate=None,
                pace_min_per_km=None,
                elevation_m=122,
                cadence_spm=168,
                power_w=None,
            ),
        ],
    )


def test_render_activity_contains_frontmatter_sections_and_split_table() -> None:
    renderer = MarkdownRenderer()

    markdown = renderer.render_activity(build_activity(), notes="#chaleur #chaussures")

    assert markdown.startswith("---\n")
    assert 'activity_id: "123456789"' in markdown
    assert 'date: "2026-04-19"' in markdown
    assert 'schema_version: "1.2"' in markdown
    assert "## Performance" in markdown
    assert "## Dynamiques de Course & Puissance" in markdown
    assert "| Puissance moyenne | 256 W |" in markdown
    assert "| Longueur de foulee | 1.2 m |" in markdown
    assert "| Temps de contact au sol | 241 ms |" in markdown
    assert "| Ratio vertical | 7.4 % |" in markdown
    assert "| Stamina fin | 43 |" in markdown
    assert "| Stamina min | 39 |" in markdown
    assert "## Physiologie Et Recuperation" in markdown
    assert "## Tours" in markdown
    assert "- Dénivelé négatif: 74 m" in markdown
    assert "| Tour | Type | Dist | Temps | Allure | FC moy | FC max | D+ | D- |" in markdown
    assert "| 1 | Échauffement | 0.40 km | 01:18 | 3:15/km | 137 | 149 | 8 m | 2 m |" in markdown
    assert "| 2 | Récupération | 0.60 km | 03:50 | 6:23/km | 144 | 153 | 4 m | 1 m |" in markdown
    assert "## Temps dans les Zones FC" in markdown
    assert "| Z1 | 02:00 |" in markdown
    assert "## Evolution Temporelle (Intervalle: 10s)" in markdown
    assert "| Temps | Dist | FC | Allure | Denivele | Cadence | Puissance (W) |" in markdown
    assert "| 00:00 | 0.01 | 131 | 5:45/km | 120 m | 166 | 248 |" in markdown
    assert "| 00:10 | 0.04 | - | - | 122 m | 168 | - |" in markdown
    assert "#chaleur #chaussures" in markdown


def test_render_activity_uses_garmin_description_when_notes_are_missing() -> None:
    renderer = MarkdownRenderer()
    activity = build_activity().model_copy(
        update={"source_payload": {"description": "#fatigue Bonnes sensations"}}
    )

    markdown = renderer.render_activity(activity)

    assert "#fatigue Bonnes sensations" in markdown
    assert "Non renseigné" not in markdown


def test_render_activity_uses_summary_comments_when_root_description_is_missing() -> None:
    renderer = MarkdownRenderer()
    activity = build_activity().model_copy(
        update={"source_payload": {"summaryDTO": {"comments": "#pluie jambes lourdes"}}}
    )

    markdown = renderer.render_activity(activity)

    assert "#pluie jambes lourdes" in markdown
    assert "Non renseigné" not in markdown


def test_render_activity_uses_metadata_notes_when_present() -> None:
    renderer = MarkdownRenderer()
    activity = build_activity().model_copy(
        update={"source_payload": {"metadataDTO": {"notes": "#vent séance solide"}}}
    )

    markdown = renderer.render_activity(activity)

    assert "#vent séance solide" in markdown
    assert "Non renseigné" not in markdown


def test_render_activity_displays_body_battery_impact_when_start_and_end_are_missing() -> None:
    renderer = MarkdownRenderer()
    activity = build_activity().model_copy(
        update={
            "physiology": build_activity().physiology.model_copy(
                update={
                    "body_battery_start": None,
                    "body_battery_end": None,
                    "body_battery_impact": -11,
                }
            )
        }
    )

    markdown = renderer.render_activity(activity)

    assert "| Impact seance | -11 |" in markdown
    assert "| Body Battery debut | Non disponible |" in markdown
    assert "| Body Battery fin | Non disponible |" in markdown


def test_render_activity_logs_available_keys_when_garmin_notes_are_missing(
    capsys,
) -> None:
    renderer = MarkdownRenderer()
    activity = build_activity().model_copy(
        update={"source_payload": {"foo": "bar", "summaryDTO": {"baz": "qux"}}}
    )

    markdown = renderer.render_activity(activity)
    captured = capsys.readouterr()

    assert "Non renseigné" in markdown
    assert captured.out == ""


def test_render_batch_contains_period_frontmatter_summary_and_activity() -> None:
    renderer = MarkdownRenderer()

    markdown = renderer.render_batch([build_activity()], notes="#cycle-printemps")

    assert markdown.startswith("---\n")
    assert 'schema_version: "1.2"' in markdown
    assert "activity_count: 1" in markdown
    assert "## Resume Global" in markdown
    expected_summary_row = (
        "| 2026-04-19 | Endurance fondamentale | 10.24 km | 00:52:13 | 5:06/km | 148 |"
    )
    assert expected_summary_row in markdown
    assert "## Activite 1 - 2026-04-19" in markdown
    assert "#cycle-printemps" in markdown
