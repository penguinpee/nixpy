# -*- coding: utf-8 -*-
# Copyright © 2016, German Neuroinformatics Node (G-Node)
#
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted under the terms of the BSD License. See
# LICENSE file in the root of the Project.
import warnings
from numbers import Number
from enum import Enum

from .data_view import DataView
from .data_set import DataSet
from .entity import Entity
from .source_link_container import SourceLinkContainer
from .datatype import DataType
from .dimensions import (Dimension, SampledDimension, RangeDimension,
                         SetDimension, DimensionType, DimensionContainer)
from . import util
from .compression import Compression

from .exceptions import IncompatibleDimensions
from .section import Section


class DataSliceMode(Enum):
    Index = 1
    Data = 2


class DataArray(Entity, DataSet):

    def __init__(self, nixfile, nixparent, h5group):
        super(DataArray, self).__init__(nixfile, nixparent, h5group)
        self._sources = None
        self._dimensions = None

    @classmethod
    def create_new(cls, nixfile, nixparent, h5parent, name, type_,
                   data_type, shape, compression):
        newentity = super(DataArray, cls).create_new(nixfile, nixparent,
                                                     h5parent, name, type_)
        datacompr = False
        if compression == Compression.DeflateNormal:
            datacompr = True
        newentity._h5group.create_dataset("data", shape, data_type, datacompr)
        return newentity

    def _read_data(self, sl=None):
        coeff = self.polynom_coefficients
        origin = self.expansion_origin
        sup = super(DataArray, self)
        if len(coeff) or origin:
            if not origin:
                origin = 0.0

            # when there are coefficients, convert the dtype of the returned
            # data array to double
            data = sup._read_data(sl).astype(DataType.Double)
            util.apply_polynomial(coeff, origin, data)
        else:
            data = sup._read_data(sl)
        return data

    @property
    def sources(self):
        """
        A property containing all Sources referenced by the DataArray. Sources
        can be obtained by index or their id. Sources can be removed from the
        list, but removing a referenced Source will not remove it from the
        file. New Sources can be added using the append method of the list.
        This is a read only attribute.
        """
        if self._sources is None:
            self._sources = SourceLinkContainer(self)
        return self._sources

    def append_set_dimension(self, labels=None):
        """
        Append a new SetDimension to the list of existing dimension
        descriptors.

        :returns: The newly created SetDimension.
        :rtype: SetDimension
        """
        index = len(self.dimensions) + 1
        setdim = SetDimension.create_new(self, index)
        if labels:
            setdim.labels = labels
        if self.file.auto_update_timestamps:
            self.force_updated_at()
        return setdim

    def append_sampled_dimension(self, sampling_interval, label=None,
                                 unit=None, offset=None):
        """
        Append a new SampledDimension to the list of existing dimension
        descriptors.

        :param sampling_interval: The sampling interval of the SetDimension
                                  to create.
        :type sampling_interval: float

        :returns: The newly created SampledDimension.
        :rtype: SampledDimension
        """
        index = len(self.dimensions) + 1
        smpldim = SampledDimension.create_new(self, index, sampling_interval)
        if label:
            smpldim.label = label
        if unit:
            smpldim.unit = unit
        if offset:
            smpldim.offset = offset
        if self.file.auto_update_timestamps:
            self.force_updated_at()
        return smpldim

    def append_range_dimension(self, ticks=None, label=None, unit=None):
        """
        Append a new RangeDimension to the list of existing dimension
        descriptors.

        :param ticks: The ticks of the RangeDimension to create.
        :type ticks: list of float

        :returns: The newly created RangeDimension.
        :rtype: RangeDimension
        """
        index = len(self.dimensions) + 1

        rdim = RangeDimension.create_new(self, index, ticks)
        rdim.label = label
        rdim.unit = unit
        if self.file.auto_update_timestamps:
            self.force_updated_at()
        if ticks is not None:
            rdim.ticks = ticks
        return rdim

    def delete_dimensions(self):
        """
        Delete all the dimension descriptors for this DataArray.
        """
        dimgroup = self._h5group.open_group("dimensions")
        ndims = len(dimgroup)
        for idx in range(ndims):
            del dimgroup[str(idx+1)]
        return True

    def _dimension_count(self):
        return len(self._h5group.open_group("dimensions"))

    def _get_dimension_by_pos(self, index):
        h5dim = self._h5group.open_group("dimensions").open_group(str(index))
        dimtype = h5dim.get_attr("dimension_type")
        if DimensionType(dimtype) == DimensionType.Sample:
            return SampledDimension(h5dim, index)
        elif DimensionType(dimtype) == DimensionType.Range:
            return RangeDimension(h5dim, index)
        elif DimensionType(dimtype) == DimensionType.Set:
            return SetDimension(h5dim, index)
        else:
            raise TypeError("Invalid Dimension object in file.")

    def iter_dimensions(self):
        """
        1-based index dimension iterator. The method returns a generator
        which returns the index starting from one and the dimensions.
        """
        for idx, dim in enumerate(self.dimensions):
            yield idx+1, dim

    @property
    def dtype(self):
        """
        The data type of the data stored in the DataArray.
        This is a read only property.

        :return: DataType
        """
        return self._h5group.group["data"].dtype

    @property
    def polynom_coefficients(self):
        """
        The polynomial coefficients for the calibration. By default this is
        set to a {0.0, 1.0} for a linear calibration with zero offset.
        This is a read-write property and can be set to None

        :type: list of float
        """
        return tuple(self._h5group.get_data("polynom_coefficients"))

    @polynom_coefficients.setter
    def polynom_coefficients(self, coeff):
        if not coeff:
            if self._h5group.has_data("polynom_coefficients"):
                del self._h5group["polynom_coefficients"]
        else:
            dtype = DataType.Double
            self._h5group.write_data("polynom_coefficients", coeff, dtype)
        if self.file.auto_update_timestamps:
            self.force_updated_at()

    @property
    def expansion_origin(self):
        """
        The expansion origin of the calibration polynomial.
        This is a read-write property and can be set to None.
        The default value is 0.

        :type: float
        """
        return self._h5group.get_attr("expansion_origin")

    @expansion_origin.setter
    def expansion_origin(self, origin):
        util.check_attr_type(origin, Number)
        self._h5group.set_attr("expansion_origin", origin)
        if self.file.auto_update_timestamps:
            self.force_updated_at()

    @property
    def label(self):
        """
        The label of the DataArray. The label corresponds to the label of the
        x-axis of a plot. This is a read-write property and can be set to
        None.

        :type: str
        """
        return self._h5group.get_attr("label")

    @label.setter
    def label(self, label):
        util.check_attr_type(label, str)
        self._h5group.set_attr("label", label)
        if self.file.auto_update_timestamps:
            self.force_updated_at()

    @property
    def unit(self):
        """
        The unit of the values stored in the DataArray. This is a read-write
        property and can be set to None.

        :type: str
        """
        return self._h5group.get_attr("unit")

    @unit.setter
    def unit(self, unit):
        if unit:
            unit = util.units.sanitizer(unit)
        if unit == "":
            unit = None
        util.check_attr_type(unit, str)
        self._h5group.set_attr("unit", unit)
        if self.file.auto_update_timestamps:
            self.force_updated_at()

    def get_slice(self, positions, extents=None, mode=DataSliceMode.Index):
        datadim = len(self.shape)
        if not len(positions) == datadim:
            raise IncompatibleDimensions(
                "Number of positions given ({}) does not match "
                "number of data dimensions ({})".format(
                    len(positions), datadim
                ),
                "DataArray.get_slice"
            )
        if extents and not len(extents) == datadim:
            raise IncompatibleDimensions(
                "Number of extents given ({}) does not match "
                "number of data dimensions ({})".format(
                    len(extents), datadim
                ),
                "DataArray.get_slice"
            )
        if mode == DataSliceMode.Index:
            slices = tuple(slice(p, p+e) for p, e in zip(positions, extents))
            return DataView(self, slices)
        elif mode == DataSliceMode.Data:
            return self._get_slice_bydim(positions, extents)
        else:
            raise ValueError("Invalid slice mode specified. "
                             "Supported modes are DataSliceMode.Index and "
                             "DataSliceMode.Data")

    def _get_slice_bydim(self, positions, extents):
        dpos, dext = [], []
        for dim, pos, ext in zip(self.dimensions, positions, extents):
            if dim.dimension_type in (DimensionType.Sample,
                                      DimensionType.Range):
                dpos.append(dim.index_of(pos))
                dext.append(dim.index_of(pos+ext)-dpos[-1])
            elif dim.dimension_type == DimensionType.Set:
                dpos.append(int(pos))
                dext.append(int(ext))
        slices = tuple(slice(p, p+e) for p, e in zip(dpos, dext))
        return DataView(self, slices)

    @property
    def data(self):
        """
        DEPRECATED DO NOT USE ANYMORE! Returns self

        :type: :class:`~nixio.data_array.DataArray`
        """
        warnings.warn("Call to deprecated property DataArray.data",
                      category=DeprecationWarning)
        return self

    @property
    def dimensions(self):
        """
        A property containing all dimensions of a DataArray. Dimensions can be
        obtained via their index. Adding dimensions is done using the
        respective append methods for dimension descriptors.
        This is a read only attribute.

        :type: Container of dimension descriptors.
        """
        if self._dimensions is None:
            self._dimensions = DimensionContainer("dimensions", self.file,
                                                  self, Dimension)
        return self._dimensions

    # metadata
    @property
    def metadata(self):
        """

        Associated metadata of the entity. Sections attached to the entity via
        this attribute can provide additional annotations. This is an optional
        read-write property, and can be None if no metadata is available.

        :type: Section
        """
        if "metadata" in self._h5group:
            return Section(self.file, None,
                           self._h5group.open_group("metadata"))
        else:
            return None

    @metadata.setter
    def metadata(self, sect):
        if not isinstance(sect, Section):
            raise TypeError("{} is not of type Section".format(sect))
        self._h5group.create_link(sect, "metadata")

    @metadata.deleter
    def metadata(self):
        if "metadata" in self._h5group:
            self._h5group.delete("metadata")
