# -*- coding: utf-8 -*-
import pytest
import logging
import datetime

from pprint import pprint as pp

from cyvcf2 import VCF
import yaml
import pymongo


from pandas import DataFrame
# Adapter stuff
from mongomock import MongoClient
from scout.adapter.mongo import MongoAdapter as PymongoAdapter

from scout.utils.handle import get_file_handle

from scout.parse.case import parse_case
from scout.parse.panel import parse_gene_panel
from scout.parse.variant import parse_variant
from scout.parse.variant.headers import parse_rank_results_header
from scout.parse.hgnc import parse_hgnc_genes
from scout.parse.ensembl import (parse_ensembl_transcripts, parse_transcripts)
from scout.parse.exac import parse_exac_genes
from scout.parse.hpo import (parse_hpo_phenotypes, parse_hpo_genes, parse_hpo_diseases)

from scout.utils.link import link_genes
from scout.log import init_log
from scout.build import (build_institute, build_case, build_panel)
from scout.build.variant import build_variant
from scout.build.genes.hgnc_gene import build_hgnc_gene
from scout.build.genes.transcript import build_transcript
from scout.build.user import build_user
from scout.load import (load_hgnc_genes)
from scout.load.hpo import load_hpo
from scout.load.transcript import load_transcripts

# These are the reduced data files
from scout.demo.resources import (hgnc_reduced_path, transcripts37_reduced_path, genes37_reduced_path,
exac_reduced_path, hpogenes_reduced_path, hpoterms_reduced_path, hpo_to_genes_reduced_path,
hpo_phenotype_to_terms_reduced_path, mim2gene_reduced_path, genemap2_reduced_path,
transcripts38_reduced_path, genes38_reduced_path,)

from scout.demo import (research_snv_path, research_sv_path, clinical_snv_path,
                        clinical_sv_path, ped_path, load_path, panel_path, empty_sv_clinical_path,)

from scout.models.hgnc_map import HgncGene


DATABASE = 'testdb'
REAL_DATABASE = 'realtestdb'

root_logger = logging.getLogger()
init_log(root_logger, loglevel='INFO')
logger = logging.getLogger(__name__)


##################### Gene fixtures #####################

@pytest.fixture
def transcript_info(request):
    transcript = dict(
        chrom = '1',
        ens_gene_id = 'ENSG00000176022',
        ens_transcript_id = 'ENST00000379198',
        start = 1167629,
        end = 1170421,
        refseq_mrna = 'NM_080605',
        refseq_mrna_pred = '',
        refseq_ncrna = '',
    )

    return transcript


@pytest.fixture
def test_gene(request):
    gene = {
        # This is the hgnc id, required:
        'hgnc_id': 1,
        # The primary symbol, required
        'hgnc_symbol': 'test',
        'ensembl_id': 'ensembl1',  # required
        'build': '37',  # '37' or '38', defaults to '37', required

        'chromosome': 1,  # required
        'start': 10,  # required
        'end': 100,  # required

        'description': 'A gene',  # Gene description
        'aliases': ['test'],  # Gene symbol aliases, includes hgnc_symbol, str
        'entrez_id': 1,
        'omim_id': 1,
        'pli_score': 1.0,
        'primary_transcripts': ['NM1'],  # List of refseq transcripts (str)
        'ucsc_id': '1',
        'uniprot_ids': ['1'],  # List of str
        'vega_id': '1',
    }
    return gene

@pytest.fixture
def parsed_gene(request):
    gene_info = {
        'hgnc_id': 1,
        'hgnc_symbol': 'AAA',
        'ensembl_id': 'ENSG1',
        'chrom': '1',
        'start': 10,
        'end': 100,
        'build': '37'
    }
    return gene_info


@pytest.fixture
def genes(request, genes37_handle, hgnc_handle, exac_handle,
          mim2gene_handle, genemap_handle, hpo_genes_handle):
    """Get a dictionary with the linked genes"""
    print('')

    gene_dict = link_genes(
        ensembl_lines=genes37_handle,
        hgnc_lines=hgnc_handle,
        exac_lines=exac_handle,
        mim2gene_lines=mim2gene_handle,
        genemap_lines=genemap_handle,
        hpo_lines=hpo_genes_handle
    )

    return gene_dict

@pytest.fixture
def ensembl_genes(request, gene_bulk):
    """Return a dictionary that maps ensembl ids on genes"""
    _ensembl_genes = {}
    for gene_obj in gene_bulk:
        _ensembl_genes[gene_obj['ensembl_id']] = gene_obj
    return _ensembl_genes

@pytest.fixture
def gene_bulk(genes):
    """Return a list with HgncGene objects"""
    bulk = []
    for gene_key in genes:
        bulk.append(build_hgnc_gene(genes[gene_key]))

    return bulk

@pytest.fixture
def transcript_objs(request, parsed_transcripts):
    """Return a list with transcript objs"""
    print('')

    _transcripts = []
    for tx_id in parsed_transcripts:
        tx_info = parsed_transcripts[tx_id]
        _transcripts.append(build_transcript(tx_info))

    return _transcripts

@pytest.fixture
def transcripts_df(request, transcripts):
    """Return a list with transcript objs"""
    print('')
    df_info = dict(
        chromosome_name = [],
        ensembl_gene_id = [],
        ensembl_transcript_id = [],
        transcript_start = [],
        transcript_end = [],
        refseq_mrna = [],
        refseq_mrna_predicted = [],
        refseq_ncrna = [],
    )

    for tx_info in transcripts:
        df_info['chromosome_name'].append(tx_info['chrom'])
        df_info['ensembl_gene_id'].append(tx_info['ensembl_gene_id'])
        df_info['ensembl_transcript_id'].append(tx_info['ensembl_transcript_id'])
        df_info['transcript_start'].append(tx_info['transcript_start'])
        df_info['transcript_end'].append(tx_info['transcript_end'])
        df_info['refseq_mrna'].append(tx_info.get('refseq_mrna', ''))
        df_info['refseq_mrna_predicted'].append(tx_info.get('refseq_mrna_predicted', ''))
        df_info['refseq_ncrna'].append(tx_info.get('refseq_ncrna', ''))

    df = DataFrame(df_info)

    return df


#############################################################
################# Hpo terms fixtures ########################
#############################################################
@pytest.fixture
def hpo_terms_handle(request, hpo_terms_file):
    """Get a file handle to a hpo terms file"""
    print('')
    hpo_lines = get_file_handle(hpo_terms_file)
    return hpo_lines


@pytest.fixture
def hpo_terms(request, hpo_terms_file):
    """Get a dictionary with the hpo terms"""
    print('')
    hpo_terms_handle = get_file_handle(hpo_terms_file)
    return parse_hpo_phenotypes(hpo_terms_handle)


@pytest.fixture
def hpo_disease_handle(request, hpo_disease_file):
    """Get a file handle to a hpo disease file"""
    print('')
    handle = get_file_handle(hpo_disease_file)
    return handle


@pytest.fixture
def hpo_diseases(request, hpo_disease_file):
    """Get a file handle to a hpo disease file"""
    print('')
    hpo_disease_handle = get_file_handle(hpo_disease_file)
    diseases = parse_hpo_diseases(hpo_disease_handle)
    return diseases


#############################################################
##################### Case fixtures #########################
#############################################################
@pytest.fixture(scope='function')
def ped_lines(request):
    """Get the lines for a case"""
    case_lines = [
        "#Family ID	Individual ID	Paternal ID	Maternal ID	Sex	Phenotype",
        "643594	ADM1059A1	0	0	1	1",
        "643594	ADM1059A2	ADM1059A1	ADM1059A3	1	2",
        "643594	ADM1059A3	0	0	2	1",
    ]
    return case_lines


@pytest.fixture(scope='function')
def case_lines(request, scout_config):
    """Get the lines for a case"""
    case = parse_case(scout_config)
    return case


@pytest.fixture(scope='function')
def parsed_case(request, scout_config):
    """Get the lines for a case"""
    case = parse_case(scout_config)
    return case


@pytest.fixture(scope='function')
def case_obj(request, parsed_case):

    logger.info("Create a case obj")
    case = parsed_case
    case['_id'] = parsed_case['case_id']
    case['owner'] = parsed_case['owner']
    case['created_at'] = parsed_case['analysis_date']
    case['dynamic_gene_list'] = {}
    case['genome_version'] = None
    case['has_svvariants'] = True

    case['individuals'][0]['sex'] = '1'
    case['individuals'][1]['sex'] = '1'
    case['individuals'][2]['sex'] = '2'

    case['is_migrated'] = False
    case['is_research'] = False

    case['panels'] = [
        {
                'display_name': 'Test panel',
                'is_default': True,
                'nr_genes': 263,
                'panel_id': 'panel1',
                'panel_name': 'panel1',
                'updated_at': datetime.datetime(2018, 4, 25, 15, 43, 44, 823465),
                'version': 1.0
        }
    ]
    case['rerun_requested']= False
    case['research_requested'] = False
    case['status'] = 'inactive'
    case['synopsis'] = ''
    case['updated_at'] = parsed_case['analysis_date']

    return case


#############################################################
##################### Clinvar fixtures ######################
#############################################################
@pytest.fixture(scope='function')
def clinvar_variant(request):
    clivar_variant = {
        '_id' : '3eecfca5efea445eec6c19a53299043b',
        '##Local_ID' : '3eecfca5efea445eec6c19a53299043b',
        'Reference_allele' : 'C',
        'Alternate_allele' : 'A',
        'Chromosome' : '7',
        'Start' : '124491972',
        'Stop' : '124491972',
        'Clinical_significance' : 'Likely Pathogenic',
        'Condition_ID_value' : 'HP:0001298;HP:0002121',
        'clinvar_submission' : 'SUB666',
    }

    return clivar_variant


#############################################################
##################### Institute fixtures ####################
#############################################################
@pytest.fixture(scope='function')
def parsed_institute(request):
    print('')
    institute = {
        'institute_id': 'cust000',
        'display_name': 'test_institute',
        'sanger_recipients': ['john@doe.com', 'jane@doe.com']
    }

    return institute


@pytest.fixture(scope='function')
def institute_obj(request, parsed_institute):
    print('')
    logger.info('Building a institute')
    institute = build_institute(
        internal_id=parsed_institute['institute_id'],
        display_name=parsed_institute['display_name'],
        sanger_recipients=parsed_institute['sanger_recipients'],
    )
    return institute


#############################################################
##################### User fixtures #########################
#############################################################
@pytest.fixture(scope='function')
def parsed_user(request, institute_obj):
    """Return user info"""
    user_info = {
        'email': 'john@doe.com',
        'name': 'John Doe',
        'location': 'here',
        'institutes': [institute_obj['internal_id']],
        'roles': ['admin']
    }
    return user_info


@pytest.fixture(scope='function')
def user_obj(request, parsed_user):
    """Return a User object"""
    _user_obj = build_user(parsed_user)
    return _user_obj


#############################################################
##################### Adapter fixtures #####################
#############################################################

# We need to mokeypatch 'connect' function so the tests use a mongomock database
# @pytest.fixture(autouse=True)
# def no_connect(monkeypatch):
#     # from scout.adapter.client import get_connection
#     mongo = Mock(return_value=MongoClient())
#     print('hej')
#
#     monkeypatch.setattr('scout.adapter.client.get_connection', mongo)

@pytest.fixture(scope='function')
def database_name(request):
    """Get the name of the test database"""
    return DATABASE

@pytest.fixture(scope='function')
def real_database_name(request):
    """Get the name of the test database"""
    return REAL_DATABASE

@pytest.fixture(scope='function')
def pymongo_client(request):
    """Get a client to the mongo database"""

    logger.info("Get a mongomock client")
    start_time = datetime.datetime.now()
    mock_client = MongoClient()

    def teardown():
        print('\n')
        logger.info("Deleting database")
        mock_client.drop_database(DATABASE)
        logger.info("Database deleted")
        logger.info("Time to run test:{}".format(datetime.datetime.now() - start_time))

    request.addfinalizer(teardown)

    return mock_client


@pytest.fixture(scope='function')
def real_pymongo_client(request):
    """Get a client to the mongo database"""

    logger.info("Get a real pymongo client")
    start_time = datetime.datetime.now()
    mongo_client = pymongo.MongoClient()

    def teardown():
        print('\n')
        logger.info("Deleting database")
        mongo_client.drop_database(REAL_DATABASE)
        logger.info("Database deleted")
        logger.info("Time to run test:{}".format(datetime.datetime.now() - start_time))

    request.addfinalizer(teardown)

    return mongo_client


@pytest.fixture(scope='function')
def real_adapter(request, real_pymongo_client):
    """Get an adapter connected to mongo database"""
    logger.info("Connecting to database...")
    mongo_client = real_pymongo_client

    logger.info("Connecting to database %s", REAL_DATABASE)

    database = mongo_client[REAL_DATABASE]
    mongo_adapter = PymongoAdapter(database)

    mongo_adapter.load_indexes()

    logger.info("Connected to database")

    return mongo_adapter


@pytest.fixture(scope='function')
def adapter(request, pymongo_client):
    """Get an adapter connected to mongo database"""
    logger.info("Connecting to database...")
    mongo_client = pymongo_client

    database = mongo_client[DATABASE]
    mongo_adapter = PymongoAdapter(database)

    logger.info("Connected to database")

    return mongo_adapter


@pytest.fixture(scope='function')
def clinvar_database(request, adapter, clinvar_variant, user_obj, institute_obj, case_obj):
    "Returns an adapter to a database populated with one variant"

    user_id = user_obj['_id']
    institute_id = institute_obj['internal_id']
    case_id = case_obj['_id']

    adapter.add_clinvar_submission([clinvar_variant], user_id, institute_id, case_id)

    return adapter


@pytest.fixture(scope='function')
def institute_database(request, adapter, institute_obj, user_obj):
    "Returns an adapter to a database populated with institute"
    adapter.add_institute(institute_obj)
    adapter.add_user(user_obj)

    return adapter


@pytest.fixture(scope='function')
def real_institute_database(request, real_adapter, institute_obj, user_obj):
    "Returns an adapter to a database populated with institute"
    adapter = real_adapter
    adapter.add_institute(institute_obj)
    adapter.add_user(user_obj)

    return adapter


@pytest.fixture(scope='function')
def gene_database(request, institute_database, genes):
    "Returns an adapter to a database populated with user, institute, case and genes"
    adapter = institute_database

    gene_objs = load_hgnc_genes(
        adapter=adapter,
        genes=genes,
        build='37'
    )

    logger.info("Creating index on hgnc collection")
    adapter.hgnc_collection.create_index([('build', pymongo.ASCENDING),
                                          ('hgnc_symbol', pymongo.ASCENDING)])

    transcripts_handle = get_file_handle(transcripts37_reduced_path)
    load_transcripts(adapter, transcripts_handle, build='37')

    adapter.transcript_collection.create_index([('build', pymongo.ASCENDING),
                                                ('hgnc_id', pymongo.ASCENDING)])

    logger.info("Index done")

    return adapter


@pytest.fixture(scope='function')
def real_gene_database(request, real_institute_database, genes37_handle, hgnc_handle, exac_handle,
                  mim2gene_handle, genemap_handle, hpo_genes_handle):
    "Returns an adapter to a database populated with user, institute, case and genes"
    adapter = real_institute_database

    load_hgnc_genes(
        adapter=adapter,
        ensembl_lines=genes37_handle,
        hgnc_lines=hgnc_handle,
        exac_lines=exac_handle,
        mim2gene_lines=mim2gene_handle,
        genemap_lines=genemap_handle,
        hpo_lines=hpo_genes_handle,
        build='37'

    )

    logger.info("Creating index on hgnc collection")
    adapter.hgnc_collection.create_index([('build', pymongo.ASCENDING),
                                          ('hgnc_symbol', pymongo.ASCENDING)])
    logger.info("Index done")

    return adapter


@pytest.fixture(scope='function')
def hpo_database(request, gene_database, hpo_terms_handle, hpo_to_genes_handle, hpo_disease_handle):
    "Returns an adapter to a database populated with hpo terms"
    adapter = gene_database


    load_hpo(
        adapter=gene_database,
        hpo_lines=get_file_handle(hpoterms_reduced_path),
        hpo_gene_lines=get_file_handle(hpo_to_genes_reduced_path),
        disease_lines=get_file_handle(genemap2_reduced_path),
        hpo_disease_lines=get_file_handle(hpo_phenotype_to_terms_reduced_path),
    )

    return adapter


@pytest.fixture(scope='function')
def real_hpo_database(request, real_gene_database, hpo_terms_handle, hpo_to_genes_handle,
                      genemap_handle, hpo_disease_handle):
    "Returns an adapter to a database populated with hpo terms"
    adapter = real_gene_database

    load_hpo(
        adapter=gene_database,
        hpo_lines=hpo_terms_handle,
        hpo_gene_lines=hpo_to_genes_handle,
        disease_lines=genemap_handle,
        hpo_disease_lines=hpo_disease_handle,
    )

    return adapter


@pytest.fixture(scope='function')
def panel_database(request, gene_database, parsed_panel):
    "Returns an adapter to a database populated with user, institute and case"
    adapter = gene_database
    logger.info("Adding panel to adapter")

    adapter.load_panel(
        parsed_panel=parsed_panel,
    )

    return adapter


@pytest.fixture(scope='function')
def real_panel_database(request, real_gene_database, parsed_panel):
    "Returns an adapter to a database populated with user, institute and case"
    adapter = real_gene_database
    logger.info("Adding panel to real adapter")

    adapter.load_panel(
        parsed_panel=parsed_panel,
    )

    return adapter


@pytest.fixture(scope='function')
def case_database(request, panel_database, parsed_case):
    "Returns an adapter to a database populated with institute, user and case"
    adapter = panel_database
    case_obj = build_case(parsed_case, adapter)
    adapter._add_case(case_obj)

    return adapter


@pytest.fixture(scope='function')
def populated_database(request, panel_database, parsed_case):
    "Returns an adapter to a database populated with user, institute case, genes, panels"
    adapter = panel_database

    logger.info("Adding case to adapter")
    case_obj = build_case(parsed_case, adapter)
    adapter._add_case(case_obj)
    return adapter


@pytest.fixture(scope='function')
def real_populated_database(request, real_panel_database, parsed_case):
    "Returns an adapter to a database populated with user, institute case, genes, panels"
    adapter = real_panel_database

    logger.info("Adding case to real adapter")
    case_obj = build_case(parsed_case, adapter)
    adapter._add_case(case_obj)

    return adapter

@pytest.fixture(scope='function')
def variant_database(request, populated_database):
    """Returns an adapter to a database populated with user, institute, case
       and variants"""
    adapter = populated_database
    # Load variants
    case_obj = adapter.case_collection.find_one()

    adapter.load_variants(
        case_obj,
        variant_type='clinical',
        category='snv',
        rank_threshold=-10,
        build='37'
    )

    return adapter


@pytest.fixture(scope='function')
def real_variant_database(request, real_populated_database):
    """Returns an adapter to a database populated with user, institute, case
       and variants"""
    adapter = real_populated_database

    case_obj = adapter.case_collection.find_one()
    # Load variants
    adapter.load_variants(
        case_obj,
        variant_type='clinical',
        category='snv',
        rank_threshold=-10,
        build='37'
    )

    return adapter


@pytest.fixture(scope='function')
def sv_database(request, populated_database, variant_objs, sv_variant_objs):
    """Returns an adapter to a database populated with user, institute, case
       and variants"""
    adapter = populated_database

    case_obj = adapter.case_collection.find_one()
    # Load sv variants
    adapter.load_variants(
        case_obj,
        variant_type='clinical',
        category='sv',
        rank_threshold=-10,
        build='37'
    )

    return adapter


#############################################################
##################### Panel fixtures #####################
#############################################################
@pytest.fixture(scope='function')
def panel_info(request):
    "Return one panel info as specified in tests/fixtures/config1.ini"
    panel = {
        'date': datetime.datetime.now(),
        'file': panel_path,
        'type': 'clinical',
        'institute': 'cust000',
        'version': '1.0',
        'panel_name': 'panel1',
        'full_name': 'Test panel'
    }
    return panel


@pytest.fixture(scope='function')
def parsed_panel(request, panel_info):
    """docstring for parsed_panels"""
    panel = parse_gene_panel(
        path=panel_info['file'],
        institute=panel_info['institute'],
        panel_id=panel_info['panel_name'],
        panel_type=panel_info['type'],
        date=panel_info['date'],
        version=panel_info['version'],
        display_name=panel_info['full_name']
    )

    return panel


@pytest.fixture(scope='function')
def panel_obj(request, parsed_panel, gene_database):
    """docstring for parsed_panels"""
    panel = build_panel(parsed_panel, gene_database)

    return panel


@pytest.fixture(scope='function')
def gene_panels(request, parsed_case):
    """Return a list with the gene panels of parsed case"""
    panels = parsed_case['gene_panels']

    return panels


@pytest.fixture(scope='function')
def default_panels(request, parsed_case):
    """Return a list with the gene panels of parsed case"""
    panels = parsed_case['default_panels']

    return panels


#############################################################
##################### Variant fixtures #####################
#############################################################
@pytest.fixture(scope='function')
def basic_variant_dict(request):
    """Return a variant dict with the required information"""
    variant = {
        'CHROM': '1',
        'ID': '.',
        'POS': '10',
        'REF': 'A',
        'ALT': 'C',
        'QUAL': '100',
        'FILTER': 'PASS',
        'FORMAT': 'GT',
        'INFO': '.',
        'info_dict': {},
    }
    return variant


@pytest.fixture(scope='function')
def one_variant(request, variant_clinical_file):
    logger.info("Return one parsed variant")
    variant_parser = VCF(variant_clinical_file)

    for variant in variant_parser:
        break

    return variant


@pytest.fixture(scope='function')
def one_sv_variant(request, sv_clinical_file):
    logger.info("Return one parsed SV variant")
    variant_parser = VCF(sv_clinical_file)

    for variant in variant_parser:
        break

    return variant


@pytest.fixture(scope='function')
def rank_results_header(request, variant_clinical_file):
    logger.info("Return a VCF parser with one variant")
    variants = VCF(variant_clinical_file)
    rank_results = parse_rank_results_header(variants)

    return rank_results


@pytest.fixture(scope='function')
def sv_variants(request, sv_clinical_file):
    logger.info("Return a VCF parser many svs")
    variants = VCF(sv_clinical_file)
    return variants


@pytest.fixture(scope='function')
def variants(request, variant_clinical_file):
    logger.info("Return a VCF parser many svs")
    variants = VCF(variant_clinical_file)
    return variants


@pytest.fixture(scope='function')
def parsed_variant(request, one_variant, case_obj):
    """Return a parsed variant"""
    print('')
    variant_dict = parse_variant(one_variant, case_obj)
    return variant_dict


@pytest.fixture(scope='function')
def variant_obj(request, parsed_variant):
    """Return a variant object"""
    print('')
    institute_id = 'cust000'
    variant = build_variant(parsed_variant, institute_id=institute_id)
    return variant


@pytest.fixture(scope='function')
def cyvcf2_variant():
    """Return a variant object"""
    print('')

    class Cyvcf2Variant(object):
        def __init__(self):
            self.CHROM = '1'
            self.REF = 'A'
            self.ALT = ['C']
            self.POS = 10
            self.end = 11
            self.FILTER = None
            self.ID = '.'
            self.QUAL = None
            self.var_type = 'snp'
            self.INFO = {'RankScore': "123:10"}

    variant = Cyvcf2Variant()
    return variant


# @pytest.fixture(scope='function')
# def parsed_variant():
#     """Return variant information for a parsed variant with minimal information"""
#     variant = {'alternative': 'C',
#                'callers': {
#                    'freebayes': None,
#                    'gatk': None,
#                    'samtools': None
#                },
#                'case_id': 'cust000-643594',
#                'category': 'snv',
#                'chromosome': '2',
#                'clnsig': [],
#                'compounds': [],
#                'conservation': {'gerp': [], 'phast': [], 'phylop': []},
#                'dbsnp_id': None,
#                'end': 176968945,
#                'filters': ['PASS'],
#                'frequencies': {
#                    'exac': None,
#                    'exac_max': None,
#                    'thousand_g': None,
#                    'thousand_g_left': None,
#                    'thousand_g_max': None,
#                    'thousand_g_right': None},
#                'genes': [],
#                'genetic_models': [],
#                'hgnc_ids': [],
#                'ids': {'display_name': '1_10_A_C_clinical',
#                        'document_id': 'a1f1d2ac588dae7883f474d41cfb34b8',
#                        'simple_id': '1_10_A_C',
#                        'variant_id': 'e8e33544a4745f8f5a09c5dea3b0dbe4'},
#                'length': 1,
#                'local_obs_hom_old': None,
#                'local_obs_old': None,
#                'mate_id': None,
#                'position': 176968944,
#                'quality': 10.0,
#                'rank_score': 0.0,
#                'reference': 'A',
#                'samples': [{'alt_depth': -1,
#                             'display_name': 'NA12882',
#                             'genotype_call': None,
#                             'genotype_quality': None,
#                             'individual_id': 'ADM1059A2',
#                             'read_depth': None,
#                             'ref_depth': -1},
#                            {'alt_depth': -1,
#                             'display_name': 'NA12877',
#                             'genotype_call': None,
#                             'genotype_quality': None,
#                             'individual_id': 'ADM1059A1',
#                             'read_depth': None,
#                             'ref_depth': -1},
#                            {'alt_depth': -1,
#                             'display_name': 'NA12878',
#                             'genotype_call': None,
#                             'genotype_quality': None,
#                             'individual_id': 'ADM1059A3',
#                             'read_depth': None,
#                             'ref_depth': -1}],
#                'sub_category': 'snv',
#                'variant_type': 'clinical'}
#     return variant


@pytest.fixture(scope='function')
def parsed_sv_variant(request, one_sv_variant, case_obj):
    """Return a parsed variant"""
    print('')
    variant_dict = parse_variant(one_sv_variant, case_obj)
    return variant_dict


@pytest.fixture(scope='function')
def parsed_variants(request, variants, case_obj):
    """Get a generator with parsed variants"""
    print('')
    individual_positions = {}
    for i, ind in enumerate(variants.samples):
        individual_positions[ind] = i

    return (parse_variant(variant, case_obj,
                          individual_positions=individual_positions)
            for variant in variants)


@pytest.fixture(scope='function')
def parsed_sv_variants(request, sv_variants, case_obj):
    """Get a generator with parsed variants"""
    print('')
    individual_positions = {}
    for i, ind in enumerate(sv_variants.samples):
        individual_positions[ind] = i

    return (parse_variant(variant, case_obj,
                          individual_positions=individual_positions)
            for variant in sv_variants)


@pytest.fixture(scope='function')
def variant_objs(request, parsed_variants, institute_obj):
    """Get a generator with parsed variants"""
    print('')
    return (build_variant(variant, institute_obj)
            for variant in parsed_variants)


@pytest.fixture(scope='function')
def sv_variant_objs(request, parsed_sv_variants, institute_obj):
    """Get a generator with parsed variants"""
    print('')
    return (build_variant(variant, institute_obj)
            for variant in parsed_sv_variants)


#############################################################
##################### File fixtures #####################
#############################################################

@pytest.fixture
def config_file(request):
    """Get the path to a config file"""
    print('')
    return load_path


@pytest.fixture
def panel_1_file(request):
    """Get the path to a config file"""
    print('')
    return panel_path


@pytest.fixture
def hgnc_file(request):
    """Get the path to a hgnc file"""
    print('')
    return hgnc_reduced_path


@pytest.fixture
def transcripts_file(request):
    """Get the path to a ensembl transcripts file"""
    print('')
    return transcripts37_reduced_path


@pytest.fixture
def genes37_file(request):
    """Get the path to a ensembl genes file"""
    print('')
    return genes37_reduced_path

@pytest.fixture
def exac_file(request):
    """Get the path to a exac genes file"""
    print('')
    return exac_reduced_path


@pytest.fixture
def hpo_genes_file(request):
    """Get the path to the hpo genes file"""
    print('')
    return hpogenes_reduced_path


@pytest.fixture
def hpo_to_genes_file(request):
    """Get the path to the hpo to genes file"""
    print('')
    return hpo_to_genes_reduced_path


@pytest.fixture
def hpo_terms_file(request):
    """Get the path to the hpo terms file"""
    print('')
    return hpoterms_reduced_path


@pytest.fixture
def hpo_disease_file(request):
    """Get the path to the hpo disease file"""
    print('')
    return hpo_phenotype_to_terms_reduced_path


@pytest.fixture
def mim2gene_file(request):
    """Get the path to the mim2genes file"""
    print('')
    return mim2gene_reduced_path


@pytest.fixture
def genemap_file(request):
    """Get the path to the mim2genes file"""
    print('')
    return genemap2_reduced_path


@pytest.fixture(scope='function')
def variant_clinical_file(request):
    """Get the path to a variant file"""
    print('')
    return clinical_snv_path


@pytest.fixture(scope='function')
def sv_clinical_file(request):
    """Get the path to a variant file"""
    print('')
    return clinical_sv_path

@pytest.fixture(scope='function')
def empty_sv_clinical_file(request):
    """Get the path to a variant file without variants"""
    print('')
    return empty_sv_clinical_path


@pytest.fixture(scope='function')
def ped_file(request):
    """Get the path to a ped file"""
    print('')
    return ped_path


@pytest.fixture(scope='function')
def scout_config(request, config_file):
    """Return a dictionary with scout configs"""
    print('')
    in_handle = get_file_handle(config_file)
    data = yaml.load(in_handle)
    return data


@pytest.fixture(scope='function')
def minimal_config(request, scout_config):
    """Return a minimal config"""
    config = scout_config
    config.pop('madeline')
    config.pop('vcf_sv')
    config.pop('vcf_snv_research')
    config.pop('vcf_sv_research')
    config.pop('gene_panels')
    config.pop('default_gene_panels')
    config.pop('rank_model_version')
    config.pop('rank_score_threshold')
    config.pop('human_genome_build')

    return config


@pytest.fixture
def panel_handle(request, panel_1_file):
    """Get a file handle to a gene panel file"""
    print('')
    return get_file_handle(panel_1_file)


@pytest.fixture
def hgnc_handle(request, hgnc_file):
    """Get a file handle to a hgnc file"""
    print('')
    return get_file_handle(hgnc_file)


@pytest.fixture
def hgnc_genes(request, hgnc_handle):
    """Get a dictionary with hgnc genes"""
    print('')
    return parse_hgnc_genes(hgnc_handle)


@pytest.fixture
def genes37_handle(request, genes37_file):
    """Get a file handle to a ensembl gene file"""
    print('')
    return get_file_handle(genes37_file)

@pytest.fixture
def transcripts_handle(request, transcripts_file):
    """Get a file handle to a ensembl transcripts file"""
    print('')
    return get_file_handle(transcripts_file)


@pytest.fixture
def transcripts(request, transcripts_handle):
    """Get the parsed ensembl transcripts"""
    print('')
    return parse_ensembl_transcripts(transcripts_handle)

@pytest.fixture
def parsed_transcripts(request, transcripts_handle, ensembl_genes):
    """Get the parsed ensembl transcripts"""
    print('')
    transcripts = parse_transcripts(transcripts_handle)
    for tx_id in transcripts:
        tx_info = transcripts[tx_id]
        ens_gene_id = tx_info['ensembl_gene_id']
        gene_obj = ensembl_genes.get(ens_gene_id)
        if not gene_obj:
            continue
        tx_info['hgnc_id'] = gene_obj['hgnc_id']
        tx_info['primary_transcripts'] = set(gene_obj.get('primary_transcripts', []))


    return transcripts


@pytest.fixture
def exac_handle(request, exac_file):
    """Get a file handle to a ensembl gene file"""
    print('')
    return get_file_handle(exac_file)


@pytest.fixture
def exac_genes(request, exac_handle):
    """Get the parsed exac genes"""
    print('')
    return parse_exac_genes(exac_handle)


@pytest.fixture
def hpo_genes_handle(request, hpo_genes_file):
    """Get a file handle to a hpo gene file"""
    print('')
    return get_file_handle(hpo_genes_file)


@pytest.fixture
def hpo_to_genes_handle(request, hpo_to_genes_file):
    """Get a file handle to a hpo to gene file"""
    print('')
    return get_file_handle(hpo_to_genes_file)


@pytest.fixture
def hpo_disease_handle(request, hpo_disease_file):
    """Get a file handle to a hpo disease file"""
    print('')
    return get_file_handle(hpo_disease_file)


@pytest.fixture
def mim2gene_handle(request, mim2gene_file):
    """Get a file handle to a mim2genes file"""
    print('')
    return get_file_handle(mim2gene_file)


@pytest.fixture
def genemap_handle(request, genemap_file):
    """Get a file handle to a mim2genes file"""
    print('')
    return get_file_handle(genemap_file)


@pytest.fixture
def hpo_genes(request, hpo_genes_handle):
    """Get the exac genes"""
    print('')
    return parse_hpo_genes(hpo_genes_handle)


#############################################################
#################### MatchMaker Fixtures ####################
#############################################################

@pytest.fixture(scope='function')
def mme_submission():
    mme_subm_obj = {
        'patients' : [ {'id' : 'internal_id.ADM1059A2'} ],
        'created_at' : datetime.datetime(2018, 4, 25, 15, 43, 44, 823465),
        'updated_at' : datetime.datetime(2018, 4, 25, 15, 43, 44, 823465),
        'sex' : True,
        'features' : [],
        'disorders' : [],
        'genes_only' : False
    }
    return mme_subm_obj

@pytest.fixture(scope='function')
def mme_patient():
    json_patient = {
        "contact": {
          "href": "mailto:contact_email@email.com",
          "name": "A contact at an institute"
        },
        "features": [
          {
            "id": "HP:0001644",
            "label": "Dilated cardiomyopathy",
            "observed": "yes"
          },
        ],
        "genomicFeatures": [
          {
            "gene": {
              "id": "LIMS2"
            },
            "type": {
              "id": "SO:0001583",
              "label": "MISSENSE"
            },
            "variant": {
              "alternateBases": "C",
              "assembly": "GRCh37",
              "end": 128412081,
              "referenceBases": "G",
              "referenceName": "2",
              "start": 128412080
            },
            "zygosity": 1
          },
        ],
        "id": "internal_id.ADM1059A2",
        "label": "A patient for testing"
    }


@pytest.fixture(scope='function')
def match_objs():
    """Mock the results of an internal and an external match"""
    matches = [
        {    # External match where test_patient is the query and with results

            '_id' : {'$oid':'match_1'},
            'created' : {'$date': 1549964103911},
            'has_matches' : True,
            'data' : {
                'patient' : {
                    'id' : 'internal_id.ADM1059A2',
                    'contact' : {
                        'href' : 'mailto:test_contact@email.com'
                    }
                }
            },
            'results' : [
                {
                    'node' : 'external_test_node',
                    'patients' : [
                        {'patient' : {
                            'id' : 'match_1_id'},
                            'contact' : {
                                'href': 'mailto:match_user@mail.com',
                                'name' : 'Test External User'
                            },
                            'score' : {'patient' : 0.425},
                        },
                        {'patient' : {
                            'id' : 'match_2_id'},
                            'contact' : {
                                'href': 'mailto:match_user@mail.com',
                                'name' : 'Test External User'
                            },
                            'score' : {'patient' :  0.333},
                        },
                    ]
                }
            ],
            'match_type' : 'external'
        },
        {    #  Internal match where test_patient is among results
            '_id' : {'$oid':'match_2'},
            'created' : {'$date': 1549964103911},
            'has_matches' : True,
            'data' : {
                'patient' : {
                    'id' : 'external_patient_x',
                    'contact' : {
                        'href' : 'mailto:test_contact@email.com'
                    }
                }
            },
            'results' : [
                {
                    'node' : 'internal_node',
                    'patients' : [
                        {
                            'patient' : {
                            'id' : 'internal_id.ADM1059A2'},
                            'contact' : {
                                'href': 'mailto:match_user@mail.com',
                                'name' : 'Test Internal User'
                            },
                            'score' : {'patient' :  0.87},
                        },
                        {
                            'patient' : {
                            'id' : 'external_patient_y'},
                            'contact' : {
                                'href': 'mailto:match_user@mail.com',
                                'name' : 'Test Internal User'
                            },
                            'score' : {'patient' :  0.76},
                        }
                    ]
                }
            ]
            ,
            'match_type' : 'internal'
        },
    ]
    return matches
