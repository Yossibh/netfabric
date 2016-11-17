import csv

from fabric.api import *
from fabric.contrib.files import *
from fabric.utils import warn, abort, puts

REGEX_IPERF_PID_OUTPUT = 'The Iperf daemon process ID : (?P<pid>\d+)'

REGEX_IPERF_CLIENT_OUTPUT = '\[[ 0-9]+\]  [0-9.]+- *(?P<time>[0-9.]+ sec) * ' \
                            '(?P<xfer>[0-9.]+ [GMK]Bytes) *' \
                            '(?P<tput>[0-9.]+ [GMK]bits/sec)'

groups = {
    'host35': ['192.168.10.6', '192.168.10.15', '192.168.10.7', '192.168.10.8', '192.168.10.9'],
    'host36': ['192.168.20.6', '192.168.20.16', '192.168.20.7', '192.168.20.8', '192.168.20.9']
   # 'host35': ['192.168.10.6'],
   # 'host36': ['192.168.20.6']
}
env.user = 'ubuntu'
env.key_filename = '/home/ubuntu/.ssh/id_rsa'
targets = {}
# env.roledefs = {
#     'client': host35,
#     'server': host36
# }

@task
def test(client, server):
    env.roledefs = {
        'client': groups[client],
        'server': groups[server]
    }
    i=0
    for source in env.roledefs['client']:
        #print source
        targets[source] = env.roledefs['server'][i]
    execute(iperf_clients)

@roles('client')
def iperf_clients():
    print env.host
    print targets[env.host]
    #print env.roledefs["server"][0]

### new code

@parallel
@roles('server')
def start_iperf_server(port=5005):
    # TODO figure out why this doesn't work consistently
    output = sudo("nohup iperf -s -p %s -D" % port)
    try:
        pid = re.compile(REGEX_IPERF_PID_OUTPUT,
                         flags=re.MULTILINE).search(output.stdout).group('pid')
        puts("found pid %s" % pid)
    except AttributeError:
        warn("could not find pid for iperf on %(host)s" % env)


def _process_iperf_client_output(output):
    rx = re.compile(REGEX_IPERF_CLIENT_OUTPUT)
    try:
        rx_matches = rx.search(output)
        return rx_matches.groupdict()
    except AttributeError:
        return None

@parallel
@roles('client')
def run_iperf_client(time=30, port=5005):
    print targets
    print env.host
    print targets[env.host]
    output = run("iperf -c {s} -t {t} -p {p}".format(s=targets[env.host], t=time, p=port))
    results = _process_iperf_client_output(output)
    return results


def print_results(results):
    sio = StringIO()
    try:
        csvwriter = csv.writer(sio)
        csvwriter.writerow([' '] + results.keys())
        for tohost in results.keys():
            row = []
            for colheader in results.keys():
                try:
                    row.append(results[tohost][colheader]['tput'])
                except (AttributeError, KeyError):
                    #data point doesn't exist due to self-test or failure
                    row.append('X')

            csvwriter.writerow([tohost] + row)
        print sio.getvalue()
    finally:
        sio.close()

#@roles('client', 'server')
def run_iperf_between_hosts(time, port):
    """Runs an iperf test from all other hosts to this host"""
    execute(start_iperf_server, port=port)
    results = execute(run_iperf_client, port=port,
                      time=time)
    execute(killall_iperf)
    return results

@task
@runs_once
def test_network(client, server, time=30, port=5001):
    """Tests paths between all hosts and outputs table of results

    Optional parameters:
     time: duration of iperf tests (default: 30s)
     port: change iperf port (default: 5005)
    """
    env.roledefs = {
        'client': groups[client],
        'server': groups[server]
    }
    i=0
    for source in env.roledefs['client']:
        #print source
        targets[source] = env.roledefs['server'][i]
        i+=1
    results = execute(run_iperf_between_hosts, time=time, port=port)
    print_results(results)


def install_iperf():
    if exists('/etc/redhat-release'):
        puts("Detected RedHat distro, installing iperf")
        sudo('yum install -y iperf')
    elif exists('/etc/debian_version'):
        puts("Detected Debian distro, installing iperf")
        sudo('apt-get install -y iperf')
    else:
        abort("Can't detect distro; giving up!")

@roles('client', 'server')
def killall_iperf():
    sudo("killall -9 iperf", warn_only=True)


def runme(cmd):
    """Runs command on all hosts"""
    run(cmd)
