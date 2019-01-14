# Copyright (C) 2012 Association of Universities for Research in Astronomy(AURA)
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     1. Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#
#     2. Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following
#       disclaimer in the documentation and/or other materials provided
#       with the distribution.
#
#     3. The name of AURA and its representatives may not be used to
#       endorse or promote products derived from this software without
#       specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY AURA ``AS IS'' AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL AURA BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
# OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR
# TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE
# USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
# DAMAGE.

"""This module defines functions that connect the core CRDS package to the
JWST CAL code and STPIPE, tailoring it to work with DATAMODELS as inputs 
and provide results in the forms required by STPIPE.
"""

import re

# ----------------------------------------------------------------------

import crds
from crds.core import log, config, exceptions, heavy_client
from crds.core import crds_cache_locking, python23

# ----------------------------------------------------------------------

# from jwst import datamodels

# ----------------------------------------------------------------------

# This is really a testing and debug convenience function,  and notably now
# the only place in this module that a direct import of datamodels occurs
# or datamodels open() occurs.
def get_refpaths_from_filename(filename, reference_file_types):
    """Test wrapper to open/close data model for get_multiple_reference_paths."""
    from .. import datamodels
    with datamodels.open(filename) as model:
        refpaths = get_multiple_reference_paths(model, reference_file_types)
    return refpaths

# ......................
    
# import memory_profiler
# @memory_profiler.profile
def get_multiple_reference_paths(dataset_model, reference_file_types):
    """Aligns JWST pipeline requirements with CRDS library top level interfaces.
    
    `dataset_model` is an open data model.

    Returns best references dict { filetype : filepath or "N/A", ... }
    """
    data_dict = _get_data_dict(dataset_model)
    refpaths = _get_refpaths(data_dict, tuple(reference_file_types))
    return refpaths

# ......................
    
def _get_data_dict(dataset_model):
    """Return the data models header dictionary based on open data 
    `dataset_model`.
    Returns a flat parameter dictionary used for CRDS bestrefs matching.
    """
    header = dataset_model.to_flat_dict(include_arrays=False)
    return _clean_flat_dict(header)

def _clean_flat_dict(header):
    """Make sure all header items returned are simple, no complex objects."""
    return { key: val for (key,val) in header.items()
             if isinstance(val, (python23.string_types,python23.long,int,float,complex,bool)) }

# ......................

def _get_refpaths(data_dict, reference_file_types):
    """Tailor the CRDS core library getreferences() call to the JWST CAL code by
    adding locking and truncating expected exceptions.   Also simplify 'NOT FOUND n/a' to
    'N/A'.  Re-interpret empty reference_file_types as "no types" instead of core
    library default of "all types."
    """
    if not reference_file_types:   # [] interpreted as *all types*.
        return {}
    try: # catch exceptions to truncate expected tracebacks
        with crds_cache_locking.get_cache_lock():
            bestrefs = crds.getreferences(data_dict, reftypes=reference_file_types, observatory="tmt")
    except crds.CrdsBadRulesError as exc:
        raise crds.CrdsBadRulesError(str(exc))
    except crds.CrdsBadReferenceError as exc:
        raise crds.CrdsBadReferenceError(str(exc))
    except crds.CrdsLookupError as exc:
        raise crds.CrdsLookupError(str(exc))
    refpaths = {filetype: filepath if "N/A" not in filepath.upper() else "N/A"
                for (filetype, filepath) in bestrefs.items()}
    return refpaths

# ----------------------------------------------------------------------

def check_reference_open(refpath):
    """Verify that `refpath` exists and is readable for the current user.

    Ignore reference path values of "N/A" or "" for checking.
    """
    if refpath != "N/A" and refpath.strip() != "":
        opened = open(refpath, "rb")
        opened.close()
    return refpath

def get_reference_file(dataset, reference_file_type):
    """
    Gets a reference file from CRDS as a readable file-like object.
    The actual file may be optionally overridden.

    Parameters
    ----------
    input_file : jwst.datamodels.ModelBase instance
        A model of the input file.  Metadata on this input file will
        be used by the CRDS "bestref" algorithm to obtain a reference
        file.

    reference_file_type : string
        The type of reference file to retrieve.  For example, to
        retrieve a flat field reference file, this would be 'flat'.

    Returns
    -------
    reference_filepath : string
        The path of the reference in the CRDS file cache.
    """
    if isinstance(dataset, python23.string_types):
        from jwst import datamodels
        with datamodels.open(dataset) as model:
            return get_multiple_reference_paths(model, [reference_file_type])[reference_file_type]
    else:
        return get_multiple_reference_paths(dataset, [reference_file_type])[reference_file_type]
        

def get_override_name(reference_file_type):
    """
    Returns the name of the override configuration parameter for the
    given reference file type.

    Parameters
    ----------
    reference_file_type : string
        A reference file type name

    Returns
    -------
    config_parameter_name : string
        The configuration parameter name to use to override the given
        reference file type.
    """
    if not re.match('^[_A-Za-z][_A-Za-z0-9]*$', reference_file_type):
        raise ValueError(
            "{0!r} is not a valid reference file type name. "
            "It must be an identifier".format(reference_file_type))
    return "override_{0}".format(reference_file_type)


def get_svn_version():
    """Return the CRDS s/w version used for determining best references."""
    return crds.__version__


def reference_uri_to_cache_path(reference_uri):
    """Convert an abstract CRDS reference file URI into an absolute path for the
    file as located in the CRDS cache.

    e.g. 'crds://jwst_miri_flat_0177.fits'  -->  
            '/grp/crds/cache/references/jwst/jwst_miri_flat_0177.fits'

    Standard CRDS cache paths are typically defined relative to the CRDS_PATH
    environment variable.  See https://jwst-crds.stsci.edu guide and top level
    page for more info on configuring CRDS.

    The default CRDS_PATH value is /grp/crds/cache, currently on the Central Store.
    """
    if not reference_uri.startswith("crds://"):
        raise exceptions.CrdsError("CRDS reference URI's should start with 'crds://' but got", repr(reference_uri))
    basename = config.pop_crds_uri(reference_uri)
    return crds.locate_file(basename, "jwst")

def get_context_used():
    """Return the context (.pmap) used for determining best references."""
    _connected, final_context = heavy_client.get_processing_mode("jwst")
    return final_context
