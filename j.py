#!/usr/bin/env python
#
# Copyright (C) 2016 VMware, Inc.
# All Rights Reserved
#

import csv
import logging
import json
import os
import pprint
import socket
import sys
import urllib
import urllib2

import HTMLParser
import argparse
import notification

DEFAULT_DOMAIN = 'SOLUTIONS'
DEFAULT_PROJECT = 'CINS'
'''
DEFAULT_USER = getpass.getuser()
change default username, since cat user name 'vmktestdevnanny'
is not accepted by HPQC.
'''
DEFAULT_USER = 'sqian'

QC_API_URI = 'http://quality-api.eng.vmware.com:8080/QCIntgrt/rest/'
QC_DOMAIN_PROJECT_API_URI = QC_API_URI + 'VSPHERE/ESX/'
QC_API_URL_RUNS = QC_DOMAIN_PROJECT_API_URI + 'runs'
QC_KEY = '7ee736ee9f0b3b4b8b93721261b4c8b5'
DEFAULT_TIMEOUT = 120
TESTCASE_NOT_FOUND = '<Error><errorType>Test instances not found</errorType>'
STEP_SIZE = 50

log = None
loglevel = os.environ.get('LOGLEVEL', logging.INFO)
logfilelevel = logging.DEBUG
logdir = None

globals_tc_result = []
globals_tcset_list = []
global_tempest_results = {}

'''
check if testcase name in hpqc contains '.',
e.g., 'ESXi.Network.VDL2.Positive.Offloading.IPv6'
or hpqc testname doesn't contain '.',
e.g.,  'PlrTlrTrafficTest'
'''
globals_name_contains_dot = False


def process_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--buildnum", help="build number")
    parser.add_argument("--domain", default=DEFAULT_DOMAIN,
                        help="hpqc domain name")
    parser.add_argument("--onlypass", action="store_true", default=False,
                        help="only upload results of passed cases")
    parser.add_argument("--project", default=DEFAULT_PROJECT,
                        help="hpqc project name")
    parser.add_argument("--user", default=DEFAULT_USER,  help="user name")
    # hpqc testset id
    parser.add_argument("--testsetid", help="hpqc testset id")
    # Test results may be got from file (-f), from vdnet result log (-v) or
    # from externl url link (-l)
    parser.add_argument("--json", help="JSON test result file")
    parser.add_argument("--vdnetdir", help="vdnet test result directory")
    parser.add_argument("--tempestdir", help="tempest test result directory")
    # hpqc fully qualified path. value eg. "Root\\Openstack\\VIO\\6.1.6"
    parser.add_argument("--testsetspath",
                        help="Fully qualified HPQC test sets path for tempest")
    parser.add_argument("--externalurl",
                        help="external url link for test result")
    parser.add_argument("--logdir", required=True,
                        help="dir to store log file")
    parser.add_argument("--no-stdout", dest="stdout", action="store_false",
                        help="Avoid logging output to stdout", default=True)

    return parser.parse_args(args)


def setup_logging(log_dir, stdout):
    logfile = os.path.join(log_dir, 'hpqctool.log')
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    logger = logging.getLogger('vdnet')
    if not stdout:
        log.propagate = False
    logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(loglevel)

    fh = logging.FileHandler(logfile)
    fh.setLevel(loglevel)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    return logger


def fetch_url(url, header=None, data=None, print_response=False):
    if header is None:
        header = {}
    if data is None:
        data = {}
    socket.setdefaulttimeout(DEFAULT_TIMEOUT)
    if header == {}:
        header = {'APIKey': QC_KEY, 'Accept': 'application/xml'}
    if data != {}:
        encoded_data = urllib.urlencode(data)
    else:
        encoded_data = None

    if encoded_data:
        log.debug('encoded_data')
        log.debug(url)
        log.debug(encoded_data)
        log.debug(header)
    print "url"
    print url
    print "url"
    print encoded_data
    print "url"
    print header
    req = urllib2.Request(url, encoded_data, header)
    try:
        response = urllib2.urlopen(req)
        ret = response.read()
        if print_response is True:
            log.debug(ret)
        return ret
    except urllib2.HTTPError, e:
        except_str = str(e.code) + str(e.msg) + str(e.headers) + \
            str(e.fp.read())
        if TESTCASE_NOT_FOUND.lower().replace(' ', '') in \
           except_str.lower().replace(' ', ''):
            return except_str
        else:
            log.error(e.code)
            log.error(e.msg)
            log.error(e.headers)
            log.error(e.fp.read())


def get_testset_list(domain, project, testset_option):
    '''
    retun the dict of test case Instance ID and Name
    '''
    tc_instanceid_name_status = []
    testset_url = QC_DOMAIN_PROJECT_API_URI
    print "--------------------------------------"
    print fetch_url(testset_url)
    print "--------------------------------------"
    return
    #+ \
    #'test-instances?testSetIDs=%s&startIndex=%d&resultSize=%d'
    testsets = testset_option.split(',')
    for testsetid in testsets:
        ret_testcount = STEP_SIZE
        step = STEP_SIZE
        start_index = 1
        times = 1
        while ret_testcount == step:
            url = testset_url % (domain, project, testsetid, start_index, step)
            qc_testset_list = fetch_url(url)
            if qc_testset_list is None:
                log.error("Failed to get the Test Set list"
                          "Please double check qcDomain/qcProject/testsetID "
                          "value and network connection to %s" % url)
                raise Exception("Failed to get the Test Set list: %s" % url)
            if TESTCASE_NOT_FOUND.lower().replace(' ', '') in \
               qc_testset_list.lower().replace(' ', ''):
                log.info("No more test instances found in testset %s" %
                         testsetid)
                ret_testcount = 0
            else:
                while True:
                    # remove invalid or special char from returned xml
                    if '&#' in qc_testset_list:
                        position = qc_testset_list.rfind('&#')
                        if qc_testset_list[position + 4] == ';':
                            qc_testset_list = qc_testset_list[:position] + \
                                qc_testset_list[position + 5:]
                    else:
                        break
                qc_testset_parser = QCTestSetListParser()
                qc_testset_parser.feed(qc_testset_list)
                tc_instanceid_name_status.extend(
                    qc_testset_parser.tc_instanceid_name_status)
                ret_testcount = qc_testset_parser.tc_count
                start_index += step
                times += 1
    log.info("Found %d testcases in testsets=%s" %
             (len(tc_instanceid_name_status), testset_option))
    log.debug(pprint.pformat(tc_instanceid_name_status))
    return tc_instanceid_name_status


def tc_output(msg, tc):
    log.info(msg)
    log.info('-' * 90)
    for result in tc:
        log.info(' ' * 2 + result['testname'].ljust(80) + result['result'])


def check_name_dot():
    global globals_tcset_list
    global globals_name_contains_dot

    if len(globals_tcset_list) == 0:
        log.error('Testset cases list need to be retrieved first')
        raise ValueError('Testset cases list need to be retrieved first')
    testname = globals_tcset_list[0][1]
    if '.' in testname:
        globals_name_contains_dot = True
        log.info("hpqc testname: '%s' includes '.'" % testname)
    else:
        globals_name_contains_dot = False
        log.info("hpqc testname: '%s' does not include '.'" % testname)


def json_dump(log_dir, name, data):
    filename = os.path.join(log_dir, "%s.json" % name)
    with open(filename, 'w') as f:
        json.dump(data, f, sort_keys=True, indent=4)


def post_results(onlypass, domain, project, testsetid, user, buildnum):
    global globals_tc_result
    global globals_tcset_list
    global globals_name_contains_dot
    # query test instance id by test case name in test set
    for tc_ret in globals_tc_result:
        hpqc_testname = tc_ret['testname']
        if globals_name_contains_dot is False:
            hpqc_testname = hpqc_testname.split('.')[-1]
        # test case may not exist in wanted testset, so do a check.
        tc = [x for x in globals_tcset_list
              if x[1] == hpqc_testname]
        if len(tc):
            tc_ret['testinstanceid'] = tc[0][0]

    # filter cases whose name can't be found in testset
    # filter passed vs failed cases
    tc_notfound = [x for x in globals_tc_result
                   if 'testinstanceid' not in x]
    tc_passed = [x for x in globals_tc_result
                 if 'testinstanceid' in x and x['result'] == 'Passed']
    tc_failed = [x for x in globals_tc_result
                 if 'testinstanceid' in x and x['result'] == 'Failed']
    url = QC_API_URL_RUNS % (domain, project)

    def upload_results(url, user, buildnum, tc_list, status):
        data = {'tester': user,
                'testInstanceIDs': ','.join(x['testinstanceid'] for
                                            x in tc_list),
                'status': status,
                'build': buildnum}
        ret = fetch_url(url, data=data)
        if ret is None:
            log.error('Failed to upload test results')
            raise Exception('Failed to upload test results')
        else:
            log.debug(ret)
            tc_output('Succeeded to upload %s cases' % status, tc_list)

    if len(tc_passed) > 0:
        upload_results(url, user, buildnum, tc_passed, 'Passed')

    if len(tc_failed) > 0 and onlypass is False:
        upload_results(url, user, buildnum, tc_failed, 'Failed')

    if tc_notfound:
        json_dump(logdir, 'hpqc_testcase_not_found', tc_notfound)
        subject = "Testcases NOT FOUND in testset[s]: %s" % testsetid
        body = ["  %s NOT_FOUND" % (x['testname'].ljust(80))
                for x in tc_notfound]
        notification.send_email(subject, body)


def query_buildnum(vdnetdir):
    '''
    Query build number from vdnet test result directory
    '''
    buildnum = None
    testbed_json = vdnetdir + '/config.json'
    if not os.path.isfile(testbed_json):
        raise ValueError("File doesn't exist: %s" % testbed_json)
    with open(testbed_json, 'r') as testbed_json_fp:
        jsonString = testbed_json_fp.read()
        jsonObj = json.loads(jsonString)
        if 'nsxmanager' in jsonObj:
            for _, info in jsonObj['nsxmanager'].iteritems():
                if 'build' in info:
                    buildnum = info['build']
                    break
        elif 'esx' in jsonObj:
            for _, info in jsonObj['esx'].iteritems():
                if 'build' in info:
                    buildnum = info['build']
                    break
        elif 'vc' in jsonObj:
            for _, info in jsonObj['vc'].iteritems():
                if 'build' in info:
                    buildnum = info['build']
                    break

        if not buildnum:
            raise ValueError("Cannot find a proper buildnum in %s" %
                             testbed_json)
    return buildnum


def parse_vdnet_result(vdnetdir, buildnum):
    '''
    1. get test results from vdnet test log directory for later upload
    2. query build number from vdnet test log if which is not supplied
       in command options.
    '''
    global globals_tc_result
    globals_tc_result = []
    # test results may be found from testinfo.csv,
    # wiki.eng.vmware.com/CAT#Provide_CAT_testinfo.csv_File_Workload_Support
    testinfo_csv = vdnetdir + '/testinfo.csv'
    if not os.path.isfile(testinfo_csv):
        log.error("File testinfo.csv doesn't exist'")
        raise ValueError("File testinfo.csv doesn't exist'")
    invalid_run = False
    with open(testinfo_csv, 'rb') as csvfile:
        testinfo_reader = csv.reader(csvfile)
        for row in testinfo_reader:
            if len(row) < 3:
                log.warning("Invalid line (%s) in file (%s)" %
                            (row, testinfo_csv))
                continue
            tc_ret = {}
            tmp_a = row[1].split('.')
            case_name = '.'.join(tmp_a[1:])
            if not case_name:
                invalid_run = True
                log.info("Skipping invalid run: %s" % row)
                continue
            tc_ret['testname'] = case_name
            if row[2] == '0':
                tc_ret['result'] = 'Passed'
                globals_tc_result.append(tc_ret)
            elif row[2] == '1':
                tc_ret['result'] = 'Failed'
                globals_tc_result.append(tc_ret)
            else:
                log.warning("Skip uploading result for case %s" % case_name)

    if not invalid_run and len(globals_tc_result) == 0:
        raise RuntimeError('vdnet dir empty or no test runs in the dir')

    tc_output('Test cases results from vdnet log folder:', globals_tc_result)

    # query build number from vdnet log if it's not provided in cmd options
    if buildnum is None:
        buildnum = query_buildnum(vdnetdir)
        log.info('get build number: %s from vdnet log' % buildnum)
    return buildnum


def parse_tempest_result(tempestdir):
    '''
    Based on the tempest directory parse results from html files.
    '''
    global globals_tc_result
    global global_tempest_results
    globals_tc_result = []
    html_files = [os.path.join(tempestdir, f) for f in os.listdir(tempestdir)
                  if (os.path.isfile(os.path.join(tempestdir, f)) and
                      f.endswith(".html"))]
    if len(html_files) == 0:
        raise RuntimeError("No HTML file to parse.")
    tempest_result_parser = TempestResultParser()
    for filename in html_files:
        with open(filename, 'r') as f:
            results_in_html_list = f.readlines()
        html_file = ""
        for line in results_in_html_list:
            html_file += line
        tempest_result_parser.feed(html_file)
        global_tempest_results.update(tempest_result_parser.result)
    log.debug("Tempest results: %s" % pprint.pformat(global_tempest_results))
    if len(global_tempest_results) == 0:
        raise RuntimeError("Tempest result is not available from HTML file")


def parse_json_result(jsonfile, buildnum):
    '''
    1. get test results from json file
    2. return build number if it is supplied in json result file.
    '''
    global globals_tc_result
    globals_tc_result = []

    revised_buildnum = None
    with open(jsonfile, 'r') as json_fp:
        jsonString = json_fp.read()
        jsonObj = json.loads(jsonString)
        if 'results' not in jsonObj:
            log.error('unknown json format, results not found')
            raise ValueError('Can not find results in json')

        if 'buildnum' in jsonObj['results'] and \
                jsonObj['results']['buildnum'] is not None:
            revised_buildnum = jsonObj['results']['buildnum']
            log.info('buildnum %s from json results' % revised_buildnum)

        if 'testcases' not in jsonObj['results']:
            log.error('unknown json format, testcases not found')
            raise ValueError('Can not find testcases in json')

        for testcase in jsonObj['results']['testcases']:
            tc_ret = {}
            tc_ret['testname'] = testcase['testname']
            tc_ret['result'] = testcase['result']
            globals_tc_result.append(tc_ret)
    tc_output('Test cases results from json directory:', globals_tc_result)

    if revised_buildnum is None:
        revised_buildnum = buildnum
    return revised_buildnum


def get_testsets_upload_results(domain, project, path_to_test_set, onlypass,
                                user, buildnum):
    '''
    1. Get the test sets.
    2. Based on each test set id update the globals_tc_result and
    3. After updating "globals_tc_result", post the results to respective
    test set ids.
    '''
    global globals_tc_result
    global global_tempest_results
    global globals_tcset_list
    test_name_index = 1
    t_result = None
    testset_url = QC_DOMAIN_PROJECT_API_URI % (domain, project) + \
        'test-sets?folderPath=%s\\' % (path_to_test_set)
    qc_testset_list = fetch_url(testset_url)
    testSets = QCTestSetsParser()
    testSets.feed(qc_testset_list)
    test_sets = testSets.test_sets_ids
    # for each test set id
    for test_set_id in test_sets:
        globals_tc_result = []
        globals_tcset_list = []
        tc_instanceid_name_status = globals_tcset_list = get_testset_list(
            domain, project, test_set_id)
        for test_instance in tc_instanceid_name_status:
            t_name = test_instance[test_name_index]
            if t_name in global_tempest_results:
                t_result = global_tempest_results[t_name]
                if t_result == "pass":
                    t_result = "Passed"
                elif t_result == "fail":
                    t_result = "Failed"
                elif t_result == "skip":
                    continue
                else:
                    raise ValueError("result value expected pass "
                                     "or fail or skip but got %s" %
                                     t_result)
                globals_tc_result.append(
                    {'testname': t_name, 'result': t_result})
            else:
                log.warning("Missing test %s from testmpest results" % t_name)
        if len(globals_tc_result) == 0:
            # if nothing to post, continue.
            continue
        log.debug("globals_tc_result: %s " % pprint.pformat(globals_tc_result))
        log.debug("test_set_id: %s", test_set_id)
        post_results(onlypass, domain, project, test_set_id, user, buildnum)


class QCTestSetListParser(HTMLParser.HTMLParser):

    '''
    Class for getting case list of test set from QC
    '''

    def __init__(self):
        HTMLParser.HTMLParser.__init__(self)
        self.tc_instanceid_flag = False
        self.tc_name_flag = False
        self.tc_status_flag = False
        self.tc_instanceid = ''
        self.tc_name = ''
        self.tc_status = ''
        self.tc_instanceid_name_status = []
        self.tc_count = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'id':
            self.tc_instanceid_flag = True
        if tag == 'name':
            self.tc_name_flag = True
        if tag == 'status':
            self.tc_status_flag = True

    def handle_endtag(self, tag):
        if tag == 'id':
            self.tc_instanceid_flag = False
        if tag == 'name':
            self.tc_name_flag = False
        if tag == 'status':
            self.tc_status_flag = False
        if tag == 'testinstance':
            if self.tc_status == 'No Run':
                self.tc_status = ''
            else:
                self.tc_status += '-EarlierResult'
            case = (self.tc_instanceid, self.tc_name, self.tc_status, '', '')
            self.tc_instanceid_name_status.append(case)
            self.tc_instanceid = ''
            self.tc_name = ''
            self.tc_status = ''
            self.tc_count += 1

    def handle_data(self, data):
        if self.tc_instanceid_flag is True:
            self.tc_instanceid = data
        if self.tc_name_flag is True:
            self.tc_name = data
        if self.tc_status_flag is True:
            self.tc_status = data


class TempestResultParser(HTMLParser.HTMLParser):

    '''
    Class for getting tempest results into dict.
    '''

    def __init__(self):
        HTMLParser.HTMLParser.__init__(self)
        self.tc_name_flag = False
        self.tc_name = ''
        self.test_case_name = ''
        self.testcase_attribute = [('class', 'testcase')]
        self.test_attribute = [('class', 'testname')]
        self.test_status_attribute = ('class', 'popup_link')
        self.result = {}
        self.class_name_flag = False
        self.fully_qualified_test_name = ''
        self.class_name = ''
        self.test_status_flag = False
        self.test_status = ''

    def handle_starttag(self, tag, attrs):
        if tag == 'div' and attrs == self.testcase_attribute:
            self.tc_name_flag = True
        if tag == 'td' and attrs == self.test_attribute:
            self.class_name_flag = True
        if tag == 'a' and attrs[0] == self.test_status_attribute:
            self.test_status_flag = True

    def handle_endtag(self, tag):
        if tag == 'div' and self.tc_name_flag:
            self.tc_name_flag = False
        if tag == 'td' and self.class_name_flag:
            self.class_name_flag = False
        if tag == 'a' and self.test_status_flag:
            self.test_status_flag = False
            fully_qualified_test_name = (
                self.class_name + '.' + self.test_case_name)
            fully_qualified_test_name = fully_qualified_test_name.replace(
                'setUpClass (', '')
            fully_qualified_test_name = fully_qualified_test_name.replace(
                ')', '')
            self.result[fully_qualified_test_name] = self.test_status

    def handle_data(self, data):
        if self.tc_name_flag:
            self.test_case_name = data.split("[")[0]
        if self.class_name_flag:
            self.class_name = data
        if self.test_status_flag:
            self.test_status = data.strip()


class QCTestSetsParser(HTMLParser.HTMLParser):

    '''
    Class for getting test case list of test set from QC
    '''

    def __init__(self):
        HTMLParser.HTMLParser.__init__(self)
        self.tc_instanceid_flag = False
        self.test_sets_ids = []

    def handle_starttag(self, tag, attrs):
        if tag == 'id':
            self.tc_instanceid_flag = True

    def handle_endtag(self, tag):
        if tag == 'id':
            self.tc_instanceid_flag = False

    def handle_data(self, data):
        if self.tc_instanceid_flag:
            self.test_sets_ids.append(data)


def main(args):
    global globals_tcset_list
    global globals_name_contains_dot
    global log
    global logdir
    try:
        cmdOpts = process_args(args)
        logdir = cmdOpts.logdir
        log = setup_logging(cmdOpts.logdir, cmdOpts.stdout)
        log.info("hpqctool cmdOpts are %s", cmdOpts)
        if not cmdOpts.testsetspath and not cmdOpts.testsetid:
            raise Exception('testset id is missing!')
        if cmdOpts.tempestdir and not cmdOpts.testsetspath:
            log.error('HPQC testsetspath is missing!')
            raise Exception('HPQC testsetspath is missing!')
        if cmdOpts.tempestdir and not cmdOpts.buildnum:
            log.error('buildnum is missing!')
            raise Exception('buildnum is missing!')
        if cmdOpts.tempestdir:
            globals_name_contains_dot = True
        else:
            globals_tcset_list = get_testset_list(cmdOpts.domain,
                                                  cmdOpts.project,
                                                  cmdOpts.testsetid)
            check_name_dot()
        if cmdOpts.vdnetdir:
            cmdOpts.buildnum = parse_vdnet_result(cmdOpts.vdnetdir,
                                                  cmdOpts.buildnum)
            post_results(cmdOpts.onlypass, cmdOpts.domain, cmdOpts.project,
                         cmdOpts.testsetid, cmdOpts.user, cmdOpts.buildnum)
        if cmdOpts.json:
            cmdOpts.buildnum = parse_json_result(cmdOpts.json,
                                                 cmdOpts.buildnum)
            post_results(cmdOpts.onlypass, cmdOpts.domain, cmdOpts.project,
                         cmdOpts.testsetid, cmdOpts.user, cmdOpts.buildnum)
        if cmdOpts.tempestdir:
            parse_tempest_result(cmdOpts.tempestdir)
            get_testsets_upload_results(cmdOpts.domain, cmdOpts.project,
                                        cmdOpts.testsetspath, cmdOpts.onlypass,
                                        cmdOpts.user, cmdOpts.buildnum)
    except Exception as e:
        log.error("HPQC tool Failed with exception: %s", e)
        raise

if __name__ == "__main__":
    get_testset_list("VSPHERE", "ESX", "abc")
    main(sys.argv[1:])
    sys.exit(0)
