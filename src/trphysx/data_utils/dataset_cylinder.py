'''
=====
- Associated publication:
url: 
doi: 
github: 
=====
'''
import logging
import h5py
import torch
from .dataset_phys import PhysicalDataset
from ..embedding.embedding_model import EmbeddingModel

logger = logging.getLogger(__name__)

class CylinderDataset(PhysicalDataset):
    """Dataset for 2D flow around a cylinder numerical example
    """
    def embed_data(self, h5_file: h5py.File, embedder: EmbeddingModel, save_states: bool = False):
        """Embeds cylinder flow data into a 1D vector representation for the transformer.

        TODO: Remove redundant arguments

        Args:
            h5_file (h5py.File): HDF5 file object of Lorenz raw data
            embedder (EmbeddingModel): Embedding neural network
            save_states (bool, optional): To save the physical states or not, should be True for validation and testing. Defaults to False.
        """
        # Iterate through stored time-series
        samples = 0
        embedder.eval()
        for key in h5_file.keys():
            ux = torch.Tensor(h5_file[key + '/ux'])
            uy = torch.Tensor(h5_file[key + '/uy'])
            p = torch.Tensor(h5_file[key + '/p'])
            data_series = torch.stack([ux, uy, p], dim=1).to(embedder.devices[0])
            visc = (2.0 / float(key))*torch.ones(ux.size(0), 1).to(embedder.devices[0])
            with torch.no_grad():
                embedded_series = embedder.embed(data_series, visc).cpu()

            # Stride over time-series
            for i in range(0, data_series.size(0) - self.block_size + 1, self.stride):  # Truncate in block of block_size
                data_series0 = embedded_series[i: i + self.block_size]  # .repeat(1, 4)
                self.examples.append(data_series0)
                self.position_ids.append(torch.arange(0, self.block_size, dtype=torch.long)+i)
                if save_states:
                    self.states.append(data_series[i: i + self.block_size].cpu())
            samples = samples + 1
            if (self.ndata > 0 and samples >= self.ndata):  # If we have enough time-series samples break loop
                break


class CylinderPredictDataset(CylinderDataset):
    """Prediction data-set for the flow around a cylinder numerical example. Used during testing/validation
    since this data-set will store the embedding model and target states.
    TODO: Use mix-in for recover and get item methods?

    Args:
        embedder (EmbeddingModel): Embedding neural network
        file_path (str): Path to hdf5 raw data file
        block_size (int): Length of time-series blocks for training
        stride (int, optional): Stride interval to sample blocks from the raw time-series. Defaults to 1.
        neval (int, optional): Number of time-series from the HDF5 file to use for testing. Defaults to 16.
        overwrite_cache (bool, optional): Overwrite cache file if it exists, i.e. embeded the raw data from file. Defaults to False.
        cache_path (str, optional): Path to save the cached embeddings at. Defaults to None.
    """
    def __init__(self, embedder: EmbeddingModel, file_path: str, block_size: int, neval: int = 16,
                 overwrite_cache=False, cache_path=None):
        """Constructor method
        """
        super().__init__(embedder, file_path, block_size, stride=block_size, ndata=neval, save_states=True,
                         overwrite_cache=overwrite_cache, cache_path=cache_path)
        self.embedder = embedder

    @torch.no_grad()
    def recover(self, x0):
        """Recovers the physical state variables from an embedded vector

        Args:
            x0 (torch.Tensor): [B, config.n_embd] Time-series of embedded vectors

        Returns:
            (torch.Tensor): [B, 3, H, W] physical state variable tensor
        """
        x = x0.contiguous().view(-1, self.embedder.embedding_dims).to(self.embedder.devices[0])
        out = self.embedder.recover(x)
        return out.view([-1] + self.embedder.input_dims)

    def __getitem__(self, i) -> torch.Tensor:
        return {'input': self.examples[i], 'targets': self.states[i], 'positions': self.position_ids[i]}