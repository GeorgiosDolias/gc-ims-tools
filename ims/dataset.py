from ims import Spectrum
import numpy as np
import os
from glob import glob
import h5py
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import (ShuffleSplit,
    KFold, StratifiedKFold, LeaveOneOut)


class Dataset:

    def __init__(self, data, name, files, samples, labels):
        """
        DataSet class to coordinate many Spectrum instances
        as dask delayed objects with label and sample names available
        as attributes.
        Maps Spectrum methods to all spectra in DataSet and contains
        methods that require multiple spectra.

        Use one of the read_... methods as alternative constructor.

        Parameters
        ----------
        data : list
            lists instances of Spectrum

        name : str
            Uses the folder name if alternative constructor is used.

        files : list
            Lists file names of every file that
            was originally in the dataset.

        samples : list
            Lists sample names, one entry per spectrum.

        labels : list
            Lists label names, one entry per spectrum.
        """
        self.data = data
        self.name = name
        self.files = files
        self.samples = samples
        self.labels = labels
        self.preprocessing = []

    def __repr__(self):
        return f'Dataset: {self.name}, {len(self)} Spectra'

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.data[key]
        
        if isinstance(key, slice):
            return Dataset(
                self.data[key],
                self.name,
                self.files[key],
                self.samples[key],
                self.labels[key]
            )
            
        if isinstance(key, list) or isinstance(key, np.ndarray):
            return Dataset(
                [self.data[i] for i in key],
                self.name,
                [self.files[i] for i in key],
                [self.samples[i] for i in key],
                [self.labels[i] for i in key]
            )
        
    def __delitem__(self, key):
        del self.data[key]
        del self.files[key]
        del self.samples[key]
        del self.labels[key]

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    @property
    def sample_indices(self):
        """
        Property method. Gives information about where each
        sample is in the dataset.

        Returns
        -------
        dict
            Sample names as keys,
            lists with indices of spectra as values
        """
        u_samples = np.unique(self.samples)
        indices = []
        for i in u_samples:
            index = np.where(np.array(self.samples) == i)
            indices.append(index)

        indices = [list(i[0]) for i in indices]
        indices = dict(zip(u_samples, indices))
        return indices

    @staticmethod
    def _measurements(path, subfolders):
        """
        Lists paths to every file in folder.
        Optionally generates label and sample names by splitting file paths.
        """
        if subfolders:
            files = []
            samples = []
            labels = []
            paths = [os.path.normpath(i) for i in glob(f'{path}/*/*/*')]
            name = os.path.split(path)[1]
            for filedir in paths:
                file_name = os.path.split(filedir)[1]
                files.append(file_name)
                sample_name = filedir.split(os.sep)[-2]
                samples.append(sample_name)
                label = filedir.split(os.sep)[-3]
                labels.append(label)
        else:
            paths = [os.path.normpath(i) for i in glob(f'{path}/*')]
            name = os.path.split(path)[1]
            files = [os.path.split(i)[1] for i in paths]
            samples = []
            labels = []

        return (paths, name, files, samples, labels)

    @classmethod
    def read_mea(cls, path, subfolders=False):
        """
        Reads all GAS mea files in directory.

        If subfolders=True expects the following folder structure
        for each label and sample:

        Data
        |--> Group A
            |--> Sample A
                |--> file a
                |--> file b

        Labels are auto-generated from directory names.

        Parameters
        ----------
        path : str
            Directory with the data.

        subfolders : bool, optional
            Uses subdirectory names as labels,
            by default True

        Returns
        -------
        Dataset
        """
        paths, name, files, samples, labels = Dataset._measurements(
            path, subfolders
        )
        data = [Spectrum.read_mea(i) for i in paths]
        return cls(data, name, files, samples, labels)

    @classmethod
    def read_zip(cls, path, subfolders=False):
        """
        Reads zip files from GAS mea to csv converter.
        """
        paths, name, files, samples, labels = Dataset._measurements(
            path, subfolders
        )
        data = [Spectrum.read_zip(i) for i in paths]
        return cls(data, name, files, samples, labels)

    @classmethod
    def read_hdf5(cls, path):
        """
        Reads all hdf5 files generated by Spectrum.to_hdf5
        method in input directory.

        (Preferred over read_zip because it is much faster.)

        Parameters
        ----------
        path : str
            Directory with the data.

        Returns
        -------
        Dataset
            data, samples and labels attributes are not
            ordered but correctly associated.
        """
        name = os.path.split(path)[1]
        data_paths = glob(f"{path}/data/*.hdf5")
        data = [Spectrum.read_hdf5(i) for i in data_paths]

        with h5py.File(f"{path}/labels.hdf5", "r") as f:
            samples = f["samples"]
            files = f["files"]
            labels = f["labels"]

            samples = [i.decode() for i in samples]
            files = [i.decode() for i in files]
            labels = [i.decode() for i in labels]


        return cls(data, name, files, samples, labels)

    def to_hdf5(self, folder_name=None):
        """
        Exports all spectra as hdf5 files.
        Saves them to new folder.

        Parameters
        ----------
        folder_name : str, optional
            Name of new directory, the default is None.
        """
        if folder_name is None:
            folder_name = self.name

        os.mkdir(folder_name)
        path = os.path.normpath(f"{folder_name}/data")
        os.mkdir(path)

        [Spectrum.to_hdf5(i, path=path) for i in self.data]
        with h5py.File(f"{folder_name}/labels.hdf5", "w-") as f:
            f.create_dataset("samples", data=self.samples)
            f.create_dataset("labels", data=self.labels)
            f.create_dataset("files", data=self.files)
            
            
    def to_npy(self, folder_name):
        """
        Exports values of all spectra as npy file.
        Makes a target directory with a data folder
        and a npy file with label labels.

        Parameters
        ----------
        folder_name : str
            Name of new target directory.
        """
        os.mkdir(folder_name)
        os.mkdir(f'{folder_name}/data')
        le = LabelEncoder()
        labels = le.fit_transform(self.labels)
        np.save(f'{folder_name}/labels.npy', labels)
        np.save(f'{folder_name}/label_names.npy', self.labels)
        np.save(f'{folder_name}/samples.npy', self.labels)
        exports = []
        for i, j in enumerate(self.data):
            exports.append(np.save(f'{folder_name}/data/{i}', j.values))


    def select(self, label=None, sample=None):
        """
        Selects all spectra of specified label or sample.
        Must give at least one argument.

        Parameters
        ----------
        label : str, optional
            Label name to keep, by default None

        sample : str, optional
            Sample name to keep, by default None

        Returns
        -------
        Dataset
            Contains only matching spectra.
        """
        if label is None and sample is None:
            raise ValueError("Must give either label or sample value.")
        
        if label is not None:
            name = label
            indices = []
            for i, j in enumerate(self.labels):
                if j == label:
                    indices.append(i)

        if sample is not None:
            name = sample
            indices = []
            for i, j in enumerate(self.samples):
                if j == sample:
                    indices.append(i)

        result = []
        files = []
        labels = []
        samples = []
        for i in indices:
            result.append(self.data[i])
            files.append(self.files[i])
            labels.append(self.labels[i])
            samples.append(self.samples[i])

        return Dataset(
            data=result,
            name=name,
            files=files,
            samples=samples,
            labels=labels,
        )
        
    def drop(self, label=None, sample=None):
        """
        Removes all spectra of specified label or sample from Dataset.
        Must give at least one argument.

        Parameters
        ----------
        label : str, optional
            Label name to keep, by default None

        sample : str, optional
            Sample name to keep, by default None

        Returns
        -------
        Dataset
            Contains only matching spectra.
        """
        if label is None and sample is None:
            raise ValueError("Must give either label or sample value.")

        if label is not None:
            name = label
            indices = []
            for i, j in enumerate(self.labels):
                if j != label:
                    indices.append(i)

        if sample is not None:
            name = sample
            indices = []
            for i, j in enumerate(self.samples):
                if j != sample:
                    indices.append(i)

        result = []
        files = []
        labels = []
        samples = []
        for i in indices:
            result.append(self.data[i])
            files.append(self.files[i])
            labels.append(self.labels[i])
            samples.append(self.samples[i])

        return Dataset(
            data=result,
            name=name,
            files=files,
            samples=samples,
            labels=labels,
        )
        
    def add(self, spectrum, sample, label):
        """
        Adds a gcims.Spectrum to the dataset.
        Sample name and label must be provided because they are
        not stored in the Spectrum class.

        Parameters
        ----------
        spectrum : ims.gcims.Spectrum
            
        sample : str

        label : various
            Classification or Regression labels
        """        
        self.data.append(spectrum)
        self.files.append(spectrum.name)
        self.samples.append(sample)
        self.labels.append(label)
        return self

    def groupby(self, key="label"):
        """
        Groups dataset by label or sample.

        Parameters
        ----------
        key : str, optional
            "label" or "sample" are valid keys, by default "label"

        Returns
        -------
        list
            List of one ims.Dataset instance per group.
        """
        if key != "label" and key != "sample":
            raise ValueError('Only "label" or "sample" are valid keys!')
            
        result = []
        if key == "label":
            for group in np.unique(self.labels):
                result.append(self.select(label=group))
            return result

        if key == "sample":
            for sample in np.unique(self.samples):
                result.append(self.select(sample=sample))
            return result
        
    def plot(self, index=0):
        """
        Plots the spectrum of selected index and adds the label to the title.
        Equivalent to:

        Parameters
        ----------
        index : int, optional
            Index of spectrum to plot, by default 0

        Returns
        -------
        tuple
            matplotlib.figure.Figure, matplotlib.axes._subplots.AxesSubplot
        """
        ax = self[index].plot()
        plt.title(f"{self[index].name}; {self.labels[index]}")
        return ax

    def train_test_split(self, test_size=0.2, random_state=None):
        """
        Splits the dataset in train and test sets.

        Parameters
        ----------
        test_size : float, optional
            Proportion of the dataset to be used for validation.
            Should be between 0.0 and 1.0,
            by default 0.2

        random_state : int, optional
            Controls the randomness. Pass an int for reproducible output,
            by default 1

        Returns
        -------
        tuple of numpy.ndarray
            X_train, X_test, y_train, y_test
            
        Example
        -------
        >>> import ims
        >>> ds = ims.Dataset.read_mea("IMS_Data")
        >>> X_train, X_test, y_train, y_test = ds.train_test_split()
        """        
        s = ShuffleSplit(n_splits=1, test_size=test_size,
                         random_state=random_state)
        train, test = next(s.split(self.data))
        X_train, y_train = self[train].get_xy()
        X_test, y_test = self[test].get_xy()
        return X_train, X_test, y_train, y_test
    
    def kfold_split(self, n_splits=5, shuffle=True,
                    random_state=None, stratify=False):
        """
        K-Folds cross-validator (sklearn.model_selection.KFold).
        Splits the dataset into k consecutive folds and provides
        train and test data.
        
        If stratify is True uses StratifiedKfold instead.

        Parameters
        ----------
        n_splits : int, optional
            Number of folds. Must be at least 2,
            by default 5
            
        shuffle : bool, optional
            Whether to shuffle the data before splitting,
            by default True
            
        random_state : int, optional
            When shuffle is True random_state affects the order of the indice.
            Pass an int for reproducible splits,
            by default None
            
        stratify : bool, optional
            Wheter to stratify output or not.
            Preserves the percentage of samples from each class in each split.
            By default False

        Yields
        ------
        KFolds iterator
            Tuple X_train, X_test, y_train, y_test per iteration
            
        Example
        -------
        >>> import ims
        >>> ds = ims.Dataset.read_mea("IMS_Data")
        >>> model = ims.PLS_DA(ds)
        >>> for X_train, X_test, y_train, y_test in ds.kfold_split():
        >>>     model.fit(X_train, y_train)
        >>>     y_pred = model.predict(X_test, y_test)
        
        """        
        if stratify:
            kf = StratifiedKFold(n_splits=n_splits, shuffle=shuffle,
                                 random_state=random_state)
        else:
            kf = KFold(n_splits, shuffle=shuffle, random_state=random_state)

        for train_index, test_index in kf.split(self, self.labels):
            train_data = self[train_index]
            test_data = self[test_index]
            X_train, y_train = train_data.get_xy()
            X_test, y_test = test_data.get_xy()
            yield X_train, X_test, y_train, y_test
            
    def leave_one_out(self):
        """
        Leave-One-Out cross-validator.
        Provides train test splits and uses each sample once as test set
        while the remaining data is used for training.

        Yields
        -------
        tuple
            X_train, X_test, y_train, y_test
            
        Example
        -------
        >>> import ims
        >>> ds = ims.Dataset.read_mea("IMS_Data")
        >>> model = ims.PLS_DA(ds)
        >>> for X_train, X_test, y_train, y_test in ds.leave_one_out():
        >>>     model.fit(X_train, y_train)
        >>>     y_pred = model.predict(X_test, y_test)
        """ 
        loo = LeaveOneOut()
        for train_index, test_index in loo.split(self):
            train_data = self[train_index]
            test_data = self[test_index]
            X_train, y_train = train_data.get_xy()
            X_test, y_test = test_data.get_xy()
            yield X_train, X_test, y_train, y_test

    def mean(self):
        """
        Calculates means for each sample,
        in case of repeat determinations.
        Automatically groups by sample.

        Returns
        -------
        Dataset
            With mean spectra.
        """
        indices = self.sample_indices
        u_samples = np.unique(self.samples)

        labels = []
        grouped_data = []
        for i in u_samples:
            label = self.labels[indices[i][0]]
            labels.append(label)

            data = []
            index = indices[i]
            for j in index:
                data.append(self.data[j])
            grouped_data.append(data)

        means = []
        for i in grouped_data:
            means.append(sum(i) / len(i))
            
        for i, j in zip(means, u_samples):
            i.name = j

        self.data = means
        self.samples = list(u_samples)
        self.labels = labels
        self.preprocessing.append('mean')
        return self

    def tophat(self, size=15):
        """
        Applies white tophat filter on values.
        Baseline correction.
        (Slower with larger size.)

        Parameters
        ----------
        size : int, optional
            Size of structuring element, by default 15
        Returns
        -------
        Spectrum
            With tophat applied.
        """    
        self.data = [Spectrum.tophat(i, size) for i in self.data]
        self.preprocessing.append('tophat')
        return self

    def sub_first_row(self):
        """
        Subtracts first row from every row in spectrum.
        Baseline correction.

        Returns
        -------
        Spectrum
            With corrected baseline.
        """
        self.data = [Spectrum.sub_first_row(i) for i in self.data]
        self.preprocessing.append('sub_first_row')
        return self

    def interp_riprel(self):
        """
        Interpolates all spectra to common RIP relative drift time coordinate.
        Alignment along drift time coordinate.

        Returns
        -------
        Dataset
            With RIP relative spectra.
        """
        dt_riprel = []
        interp_fn = []
        for i in self.data:
            dt = i.drift_time
            rip = np.median(np.argmax(i.values, axis=1)).astype('int32')
            rip_ms = np.mean(dt[rip])
            riprel = dt / rip_ms
            f = interp1d(riprel, i.values, axis=1, kind='cubic')
            dt_riprel.append(riprel)
            interp_fn.append(f)

        start = max([i[0] for i in dt_riprel])
        end = min([i[-1] for i in dt_riprel])
        interv = np.median([(i[-1]-i[0]) / len(i) for i in dt_riprel])
        new_dt = np.arange(start, end, interv)

        for i, f in zip(self.data, interp_fn):
            i.values[:, :len(new_dt)]
            i.values = f(new_dt)
            i.drift_time = new_dt
            i._drift_time_label = 'Drift Time RIP relative'
        
        self.preprocessing.append("interp_riprel")
        return self

    def rip_scaling(self):
        """
        Scales values relative to global maximum for each spectrum.

        Returns
        -------
        Dataset
            With scaled values.
        """
        self.data = [Spectrum.rip_scaling(i) for i in self.data]
        self.preprocessing.append('rip_scaling')
        return self
    
    def resample(self, n):
        """
        Resamples spectrum by calculating means of every n rows.
        (Retention time coordinate needs to be divisible by n)

        Parameters
        ---------
        n : int

        Returns
        -------
        GCIMS-DataSet
            Resampled values array for each spectrum

        """       
        self.data = [Spectrum.resample(i, n) for i in self.data]
        self.preprocessing.append(f'resample({n})')
        return self
    
    def binning(self, n):
        """
        Downsamples each spectrum by binning the array.
        If the dims are not devisible by the binning factor
        shortens the dim by the remainder at the long end. 

        Parameters
        ----------
        n : int
            Binning factor.

        Returns
        -------
        Dataset
            Downsampled spectra
        """
        self.data = [Spectrum.binning(i, n) for i in self.data]
        self.preprocessing.append(f'binning({n})')
        return self

    def cut_dt(self, start, stop):
        """
        Cuts spectra on drift time coordinate.
        Specifiy coordinate values not index directly.

        Parameters
        ----------
        start : int/float
            start value on drift time coordinate
        
        stop : int/float
            stop value on drift time coordinate

        Returns
        -------
        Dataset
            With cut spectra.
        """
        self.data = [Spectrum.cut_dt(i, start, stop) for i in self.data]
        self.preprocessing.append(f'cut_dt({start, stop})')
        return self

    def cut_rt(self, start, stop):
        """
        Cuts spectra on retention time coordinate.
        Specifiy coordinate values not index directly.

        Parameters
        ----------
        start : int/float
            start value on retention time coordinate
        
        stop : int/float
            stop value on retention time coordinate

        Returns
        -------
        Dataset
            With cut spectra.
        """
        self.data = [Spectrum.cut_rt(i, start, stop) for i in self.data]
        self.preprocessing.append(f'cut_rt({start, stop})')
        return self

    def export_plots(self, folder_name=None, file_format='jpg', **kwargs):
        """
        Exports a static plot for each spectrum to disk.
        Replicates label folders.

        Parameters
        ----------
        folder_name : str, optional
            New directory to save the images.

        file_format : str, optional
            by default 'jpeg'
        """
        if folder_name is None:
            folder_name = self.name.join("_plots")
        group_names = np.unique(self.labels)
        sample_names = np.unique(self.samples)
        sample_indices = self.sample_indices
        os.mkdir(folder_name)
        for label in group_names:
            os.mkdir(f'{folder_name}/{label}')

        for i in sample_names:
            indices = sample_indices[i]
            for j in indices:
                label = self.labels[j]
                Spectrum.export_plot(
                    self.data[j], path=f'{folder_name}/{label}',
                    file_format=file_format, **kwargs
                    )

    def export_images(self, folder_name, file_format='jpeg'):
        """
        Exports spectrum as grayscale image for classification in Orange 3.
        (Not a plot!)

        Parameters
        ----------
        folder_name : str, optional
            New directory to save the images

        file_format : str, optional
            See imageio docs for supported formats:
            https://imageio.readthedocs.io/en/stable/formats.html,
            by default 'jpeg'
        """
        group_names = np.unique(self.labels)
        sample_names = np.unique(self.samples)
        sample_indices = self.sample_indices
        os.mkdir(folder_name)
        for group in group_names:
            os.mkdir(f'{folder_name}/{group}')

        for i in sample_names:
            indices = sample_indices[i]
            for j in indices:
                label = self.labels[j]
                Spectrum.export_image(
                    self.data[j], path=f'{folder_name}/{label}',
                    file_format=file_format
                )

    def get_xy(self, flatten=True):
        """
        Returns X and y for machine learning as
        numpy arrays.

        Parameters
        ----------
        flatten : bool, optional
            Flattens 3D datasets to 2D, by default True

        Returns
        -------
        tuple
            (X, y) as np.arrays
        """
        X = [i.values for i in self.data]
        X = np.stack(X)
        y = np.array(self.labels)

        if flatten:
            a, b, c = X.shape
            X = X.reshape(a, b*c)

        return (X, y)

    def scaling(self, method="pareto"):
        """
        Scales features according to selected method.

        Parameters
        ----------
        method : str, optional
            'pareto', 'auto' or 'var' are valid,
            by default "pareto"

        Returns
        -------
        ims.Dataset

        Raises
        ------
        ValueError
            If scaling method is not supported.
        """
        X = [i.values for i in self.data]
        X = np.stack(X)
        a, b, c = X.shape
        X = X.reshape(a, b*c)

        if method == "auto":
            weights = 1 / np.std(X, 0)
        elif method == "pareto":
            weights = 1 / np.sqrt(np.std(X, 0))
        elif method == "var":
            weights = 1 / np.var(X, 0)
        else:
            raise ValueError(f'{method} is not a supported method!')

        weights = np.nan_to_num(weights, posinf=0, neginf=0)

        X = X * weights
        for i, j in enumerate(self.data):
            j.values = X[i, :].reshape(b, c)

        self.weights = weights
        return self
