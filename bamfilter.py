# -*- coding: utf-8 -*-
#
# Copyright (c) 2010-2011, Monash e-Research Centre
#   (Monash University, Australia)
# Copyright (c) 2010-2011, VeRSI Consortium
#   (Victorian eResearch Strategic Initiative, Australia)
# All rights reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    *  Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#    *  Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#    *  Neither the name of the VeRSI, the VeRSI Consortium members, nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS ``AS IS'' AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE REGENTS AND CONTRIBUTORS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""
bamfilter.py

.. moduleauthor:: James Wettenhall <james.wettenhall@monash.edu>

"""
from fractions import Fraction
import logging

from django.conf import settings

from tardis.tardis_portal.models import Schema, DatafileParameterSet
from tardis.tardis_portal.models import ParameterName, DatafileParameter
import subprocess
import traceback
import os
import tempfile
import shutil

logger = logging.getLogger(__name__)


class BamFilter(object):
    """This filter uses samtools to get header information
    from BAM files.

    http://samtools.sourceforge.net/
    http://samtools.github.io/hts-specs/SAMv1.pdf
    http://genome.sph.umich.edu/wiki/SAM

    If a white list is specified then it takes precedence and all
    other tags will be ignored.

    :param name: the short name of the schema.
    :type name: string
    :param schema: the name of the schema to load the metadata into.
    :type schema: string
    :param tagsToFind: a list of the tags to include.
    :type tagsToFind: list of strings
    :param tagsToExclude: a list of the tags to exclude.
    :type tagsToExclude: list of strings
    """
    def __init__(self, name, schema, metadata_path,
                 tagsToFind=[], tagsToExclude=[]):
        self.name = name
        self.schema = schema
        self.tagsToFind = tagsToFind
        self.tagsToExclude = tagsToExclude
        self.metadata_path = metadata_path

    def __call__(self, sender, **kwargs):
        """post save callback entry point.

        :param sender: The model class.
        :param instance: The actual instance being saved.
        :param created: A boolean; True if a new record was created.
        :type created: bool
        """
        instance = kwargs.get('instance')

        schema = self.getSchema()

        if not instance.filename.endswith('.bam'):
            return None

        logger.info("Applying BAM filter for instance.filename = " + instance.filename)

        tmpdir = tempfile.mkdtemp()

        filepath = os.path.join(tmpdir, instance.filename)

        with instance.file_object as f:
            with open(filepath, 'wb') as g:
                while True:
                    chunk = f.read(1024)
                    if not chunk:
                        break
                    g.write(chunk)

        # filepath = instance.get_absolute_filepath()

        try:

            metadata_dump = dict()

            bin_infopath = os.path.basename(self.metadata_path)
            cd_infopath = os.path.dirname(self.metadata_path)
            cmd = "cd '%s'; ./'%s' view -H '%s'" %\
                (cd_infopath, bin_infopath, filepath)
            logger.info(cmd)
            bam_information = self.exec_command(cmd).split('\n')
            if bam_information:
                metadata_dump['bam_information'] = bam_information

            shutil.rmtree(tmpdir)

            self.saveMetadata(instance, schema, metadata_dump)

        except Exception, e:
            logger.info(e)
            return None

    def saveMetadata(self, instance, schema, metadata):
        """Save all the metadata to a DataFiles paramamter set.
        """
        parameters = self.getParameters(schema, metadata)

        if not parameters:
            logger.info("No parameters, returning None from saveMetadata.")
            return None

        try:
            ps = DatafileParameterSet.objects.get(schema=schema,
                                                  datafile=instance)
            logger.info("Parameter set already exists. Returning it.")
            return ps  # if already exists then just return it
        except DatafileParameterSet.DoesNotExist:
            logger.info("Didn't find existing datafile parameter set for schema=%s,datafile=%s" % (str(schema),str(instance)))
            ps = DatafileParameterSet(schema=schema,
                                      datafile=instance)
            logger.info("Creating datafile parameter set for schema=%s,datafile=%s" % (str(schema),str(instance)))
            ps.save()
            logger.info("Saved datafile parameter set for schema=%s,datafile=%s" % (str(schema),str(instance)))

        try:
          for p in parameters:
            logger.info(p.name)
            if p.name in metadata:
                dfp = DatafileParameter(parameterset=ps,
                                        name=p)
                if p.isNumeric():
                    if metadata[p.name] != '':
                        dfp.numerical_value = metadata[p.name]
                        dfp.save()
                else:
                    if isinstance(metadata[p.name], list):
                        for val in reversed(metadata[p.name]):
                            strip_val = val.strip()
                            if strip_val:
                                if strip_val.startswith("@HD") or \
                                        strip_val.startswith("@SQ") or \
                                        strip_val.startswith("@RG") or \
                                        strip_val.startswith("@PG"):
                                    dfp = DatafileParameter(parameterset=ps,
                                                            name=p)
                                    dfp.string_value = strip_val
                                    dfp.save()
                    else:
                        dfp.string_value = metadata[p.name]
                        dfp.save()
        except:
            logger.info(traceback.format_exc())

        return ps

    def getParameters(self, schema, metadata):
        """Return a list of the paramaters that will be saved.
        """
        param_objects = ParameterName.objects.filter(schema=schema)
        parameters = []
        for p in metadata:

            if self.tagsToFind and not p in self.tagsToFind:
                continue

            if p in self.tagsToExclude:
                continue

            parameter = filter(lambda x: x.name == p, param_objects)

            if parameter:
                parameters.append(parameter[0])
                continue

            # detect type of parameter
            datatype = ParameterName.STRING

            # Int test
            try:
                int(metadata[p])
            except ValueError:
                pass
            except TypeError:
                pass
            else:
                datatype = ParameterName.NUMERIC

            # Fraction test
            if isinstance(metadata[p], Fraction):
                datatype = ParameterName.NUMERIC

            # Float test
            try:
                float(metadata[p])
            except ValueError:
                pass
            except TypeError:
                pass
            else:
                datatype = ParameterName.NUMERIC

        return parameters

    def getSchema(self):
        """Return the schema object that the paramaterset will use.
        """
        try:
            return Schema.objects.get(namespace__exact=self.schema)
        except Schema.DoesNotExist:
            schema = Schema(namespace=self.schema, name=self.name,
                            type=Schema.DATAFILE)
            schema.save()
            return schema

    def exec_command(self, cmd):
        """execute command on shell
        """
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True)

        (stdout, stderr) = p.communicate()

        if stderr is not None and stderr.strip() != "":
            logger.info(stderr)

        result_str = stdout

        return result_str


def make_filter(name='', schema='', tagsToFind=[], tagsToExclude=[]):
    if not name:
        raise ValueError("BamFilter "
                         "requires a name to be specified")
    if not schema:
        raise ValueError("BamFilter "
                         "requires a schema to be specified")
    return BamFilter(name, schema, tagsToFind, tagsToExclude)

make_filter.__doc__ = BamFilter.__doc__
