import os
import numpy as np
import pandas as pd


class PatientStore:
    """Stable interface. Swap subclass to change backend (EHR, Postgres, etc.)."""

    def get_patient_vector(self, patient_id: str) -> np.ndarray:
        raise NotImplementedError

    def patient_exists(self, patient_id: str) -> bool:
        raise NotImplementedError

    def get_patient_label(self, patient_id: str) -> str | None:
        """Return known cancer label if available (for validation, not inference)."""
        return None

    def list_patient_ids(self) -> list[str]:
        """Return all known patient IDs."""
        raise NotImplementedError


class TCGAPatientStore(PatientStore):
    """
    Backed by TCGA-PANCAN-HiSeq-801x20531/ directory.
    - data.csv:   801 rows × 20531 gene expression columns, indexed by sample_0..sample_800
    - labels.csv: 801 rows mapping sample_id -> cancer type (BRCA, COAD, KIRC, LUAD, PRAD)

    Lazy-loads on first access so import is cheap. Subsequent lookups are O(1) from memory.
    """

    def __init__(self, data_dir: str):
        self._data_dir = data_dir
        self._data: pd.DataFrame | None = None
        self._labels: dict[str, str] = {}
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        data_path = os.path.join(self._data_dir, "data.csv")
        labels_path = os.path.join(self._data_dir, "labels.csv")
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"TCGA data not found at {data_path}")
        self._data = pd.read_csv(data_path, index_col=0)
        if os.path.exists(labels_path):
            ldf = pd.read_csv(labels_path, index_col=0)
            self._labels = ldf["Class"].to_dict()
        self._loaded = True

    def patient_exists(self, patient_id: str) -> bool:
        self._load()
        return patient_id in self._data.index

    def get_patient_vector(self, patient_id: str) -> np.ndarray:
        self._load()
        if patient_id not in self._data.index:
            raise KeyError(f"Unknown patient_id: {patient_id!r}")
        return self._data.loc[patient_id].values.astype(np.float32)

    def get_patient_label(self, patient_id: str) -> str | None:
        self._load()
        return self._labels.get(patient_id)

    def list_patient_ids(self) -> list[str]:
        self._load()
        return list(self._data.index)
