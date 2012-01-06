#!/usr/bin/env python
import pycurl
import httplib
import StringIO
import json
from threading import Thread


class Service:
    def __init__(self, url=None, username=None, password=None,
                 verify=None, agent=None):
        self.url = url
        self.username = username
        self.password = password
        self.verify = verify
        self.agent = agent


class DLError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return self.value


class TicketParams:
    pass


class Request(Thread):
    def __init__(self, dl, request, msg, file, complete_fn, failed_fn, progress_fn=None):
        super(Request, self).__init__()
        self.dl = dl
        self.request = request
        self.msg = msg
        self.file = file
        self.complete_fn = complete_fn
        self.failed_fn = failed_fn
        self.progress_fn = progress_fn
        self.cancelled = False

    def run(self):
        s = StringIO.StringIO()
        c = pycurl.Curl()
        c.setopt(c.URL, self.dl.service.url + "/" + self.request)
        c.setopt(c.WRITEFUNCTION, s.write)

        auth = {"user": self.dl.service.username, "pass": self.dl.service.password}
        post_data = [("auth", json.dumps(auth))]
        post_data.append(("msg", json.dumps(self.msg)))
        if(file):
            post_data.append(("file", (c.FORM_FILE, self.file)))

        c.setopt(c.HTTPAUTH, c.HTTPAUTH_BASIC)
        c.setopt(c.USERPWD, self.dl.service.username + ':' + self.dl.service.password)
        c.setopt(c.HTTPPOST, post_data)
        c.setopt(c.HTTPHEADER, ['Expect:', 'User-agent: ' + self.dl.service.agent])
        if not self.dl.service.verify:
            c.setopt(c.SSL_VERIFYPEER, False)

        if self.progress_fn:
            c.setopt(c.NOPROGRESS, False)
            c.setopt(c.PROGRESSFUNCTION, self.progress_fn)

        m = pycurl.CurlMulti()
        m.add_handle(c)
        num_handles = 1
        while 1:
            while 1:
                ret, num_handles = m.perform()
                if ret != pycurl.E_CALL_MULTI_PERFORM:
                    break
            if num_handles == 0 or self.cancelled:
                break
            m.select(1.0)
        m.remove_handle(c)
        code = c.getinfo(pycurl.HTTP_CODE)
        error = c.errstr()
        c.close()

        if self.cancelled:
            return self.failed_fn(None)
        if error != "":
            return self.failed_fn(DLError("DL connection error: " + error))

        ret = None
        if s.tell():
            s.seek(0)
            try:
                ret = json.load(s)
            except ValueError:
                pass

        if code != httplib.OK:
            error = httplib.responses[code]
        elif ret is not None and 'error' in ret:
            error = ret['error']
        elif ret is None:
            error = "Cannot decode output JSON"

        if error != "":
            return self.failed_fn(DLError("DL service error: " + error))
        else:
            return self.complete_fn(ret)

    def cancel(self):
        self.cancelled = True


class DL(object):
    def __init__(self, service=Service()):
        self.service = service

    def request(self, request, msg, file, async=False, complete_fn=None, failed_fn=None, progress_fn=None):
        if async:
            return Request(self, request, msg, file, complete_fn, failed_fn, progress_fn)
        else:
            ret = {}
            complete_fn_ovr = lambda msg: ret.__setitem__('ret', msg)
            failed_fn_ovr = lambda ex: ret.__setitem__('ex', ex)
            req = Request(self, request, msg, file, complete_fn_ovr, failed_fn_ovr, progress_fn)
            req.start()
            req.join()
            if 'ex' in ret:
                if failed_fn is not None:
                    failed_fn(ret['ex'])
                else:
                    raise ret['ex']
            if complete_fn is not None:
                complete_fn(ret['ret'])
            return ret['ret']

    def new_ticket(self, file, params=TicketParams(), async=False, complete_fn=None, failed_fn=None, progress_fn=None):
        return self.request("newticket", {}, file, async, complete_fn, failed_fn, progress_fn)
