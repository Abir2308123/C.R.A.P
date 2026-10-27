
import json
import tempfile
import unittest
from pathlib import Path

import dossier
from dossier import DossierService, PlantStore


class TestDossier(unittest.TestCase):

    def setUp(self):
        # Give each test its own temporary storage file.
        self.temp_dir = tempfile.TemporaryDirectory()
        file_path = Path(self.temp_dir.name) / "plants.json"

        self.service = DossierService(
            store=PlantStore(file_path=file_path)
        )

    def tearDown(self):
        # Clean up temporary files after each test.
        self.temp_dir.cleanup()

    def test_register_plant(self):
        plant = self.service.register_plant(
            plant_id="PLANT001",
            location="A1",
            species="tomato",
        )

        loaded = self.service.get_plant("PLANT001")

        self.assertEqual(loaded.plant_id, "PLANT001")
        self.assertEqual(loaded.location, "A1")
        self.assertEqual(loaded.species, "tomato")
        self.assertEqual(plant.current_status, "unassessed")

    def test_observations_preserve_history(self):
        self.service.register_plant("PLANT001", "A1")

        first = self.service.submit_observation(
            plant_id="PLANT001",
            visual_symptoms=["yellow_leaves"],
            sensor_readings={"moisture": 28.5, "ph": None},
            source="camera",
        )

        second = self.service.submit_observation(
            plant_id="PLANT001",
            visual_symptoms=["wilting"],
            sensor_readings={"moisture": 22.0},
            source="camera",
        )

        plant = self.service.get_plant("PLANT001")

        self.assertEqual(len(plant.observations), 2)
        self.assertEqual(
            plant.observations[0].observation_id,
            first.observation_id,
        )
        self.assertEqual(
            plant.observations[1].observation_id,
            second.observation_id,
        )
        self.assertIsNone(
            plant.observations[0].sensor_readings["ph"]
        )

    def test_duplicate_plant_id_is_rejected(self):
        self.service.register_plant("PLANT001", "A1")

        with self.assertRaises(ValueError):
            self.service.register_plant("PLANT001", "A2")

    def test_data_survives_reload(self):
        self.service.register_plant("PLANT001", "A1")

        self.service.submit_observation(
            plant_id="PLANT001",
            visual_symptoms=["brown_spots"],
        )

        # Simulate restarting the service using the same file.
        file_path = self.service.store.file_path
        restarted_service = DossierService(
            store=PlantStore(file_path=file_path)
        )

        plant = restarted_service.get_plant("PLANT001")

        self.assertEqual(len(plant.observations), 1)
        self.assertEqual(
            plant.observations[0].visual_symptoms,
            ["brown_spots"],
        )

    def test_json_file_contains_saved_records(self):
        self.service.register_plant("PLANT001", "A1")

        file_path = self.service.store.file_path

        with file_path.open("r", encoding="utf-8") as file:
            saved_data = json.load(file)

        self.assertEqual(len(saved_data), 1)
        self.assertEqual(saved_data[0]["plant_id"], "PLANT001")

    def test_empty_file_loads_as_no_plants(self):
        file_path = self.service.store.file_path
        file_path.write_text("", encoding="utf-8")

        self.assertEqual(self.service.list_plants(), [])

        # Registering a plant should still work on top of the empty file.
        self.service.register_plant("PLANT001", "A1")
        self.assertEqual(len(self.service.list_plants()), 1)

    def test_default_path_is_inside_package(self):
        store = PlantStore()

        self.assertEqual(
            store.file_path,
            Path(dossier.__file__).parent / "data" / "plants.json",
        )

    def test_diagnoses_survive_reload(self):
        self.service.register_plant("PLANT001", "A1")

        diagnosis = self.service.record_diagnosis(
            plant_id="PLANT001",
            possible_condition="nitrogen_deficiency",
            supporting_evidence=["yellow_leaves"],
            contradicting_evidence=["moisture_normal"],
            confidence=0.6,
        )

        file_path = self.service.store.file_path
        restarted_service = DossierService(
            store=PlantStore(file_path=file_path)
        )

        plant = restarted_service.get_plant("PLANT001")

        self.assertEqual(len(plant.diagnoses), 1)
        loaded = plant.diagnoses[0]
        self.assertEqual(loaded.diagnosis_id, diagnosis.diagnosis_id)
        self.assertEqual(loaded.timestamp, diagnosis.timestamp)
        self.assertEqual(loaded.possible_condition, "nitrogen_deficiency")
        self.assertEqual(loaded.supporting_evidence, ["yellow_leaves"])
        self.assertEqual(loaded.contradicting_evidence, ["moisture_normal"])
        self.assertEqual(loaded.confidence, 0.6)
        self.assertEqual(loaded.status, "suspected")

    def test_actions_survive_reload(self):
        self.service.register_plant("PLANT001", "A1")

        observation = self.service.submit_observation(
            plant_id="PLANT001",
            visual_symptoms=["yellow_leaves"],
        )

        action = self.service.record_action(
            plant_id="PLANT001",
            action_type="reinspect",
            reason="Confirm yellowing after 24 hours",
            status="completed",
            result="symptoms_unchanged",
            verification_observation_id=observation.observation_id,
        )

        file_path = self.service.store.file_path
        restarted_service = DossierService(
            store=PlantStore(file_path=file_path)
        )

        plant = restarted_service.get_plant("PLANT001")

        self.assertEqual(len(plant.actions), 1)
        loaded = plant.actions[0]
        self.assertEqual(loaded.action_id, action.action_id)
        self.assertEqual(loaded.timestamp, action.timestamp)
        self.assertEqual(loaded.action_type, "reinspect")
        self.assertEqual(loaded.reason, "Confirm yellowing after 24 hours")
        self.assertEqual(loaded.status, "completed")
        self.assertEqual(loaded.result, "symptoms_unchanged")
        self.assertEqual(
            loaded.verification_observation_id,
            observation.observation_id,
        )

    def test_records_keep_separate_histories(self):
        self.service.register_plant("PLANT001", "A1")
        self.service.register_plant("PLANT002", "A2")

        self.service.record_diagnosis("PLANT001", "leaf_blight")
        self.service.record_action("PLANT002", "reinspect", "Routine check")

        first = self.service.get_plant("PLANT001")
        second = self.service.get_plant("PLANT002")

        self.assertEqual(len(first.diagnoses), 1)
        self.assertEqual(len(first.actions), 0)
        self.assertEqual(len(second.diagnoses), 0)
        self.assertEqual(len(second.actions), 1)


if __name__ == "__main__":
    unittest.main()
