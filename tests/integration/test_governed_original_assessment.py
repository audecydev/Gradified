from dataclasses import replace
import pytest
from grading.integration.governed_original_assessment import (
    GovernedOriginalFact, GovernedOriginalKey, ProductionGovernedOriginalAssessment,
)
from grading.integration.governed_result_disposition import ResultDisposition

KEY = GovernedOriginalKey('TENANT-A', 'RUN-1', 'RESULT-1', 'SOURCE-1', 'POLICY-1', 'REV-1')

class Scored:
    def __init__(self, value=True): self.value=value; self.calls=0
    def read_scored_original(self, *, original):
        self.calls+=1
        return GovernedOriginalFact(original, self.value)
class Academic:
    def __init__(self, value=True): self.value=value; self.calls=0
    def read_academic_original(self, *, original):
        self.calls+=1
        return GovernedOriginalFact(original, self.value)
class Teacher:
    def __init__(self, value=True): self.value=value; self.calls=0
    def read_teacher_original(self, *, original):
        self.calls+=1
        return GovernedOriginalFact(original, self.value)
class Policy:
    def __init__(self, value=True): self.value=value; self.calls=0
    def read_adverse_policy(self, *, original):
        self.calls+=1
        return GovernedOriginalFact(original, self.value)

def rig(*, s=True, a=True, t=True, p=True):
    readers=(Scored(s),Academic(a),Teacher(t),Policy(p))
    owner=ProductionGovernedOriginalAssessment(scored=readers[0],academic=readers[1],
        teacher=readers[2],adverse_policy=readers[3],max_identifier_characters=128)
    return owner,readers

def test_genuine_four_original_reads_positive_nonpublishing():
    owner,readers=rig()
    d=owner.assess(original=KEY)
    assert d.disposition is ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF
    assert (d.tenant_ref,d.grading_run_id,d.source_revision)==('TENANT-A','RUN-1','SOURCE-1')
    assert not d.authorizes_publication and not d.authorizes_retry
    assert all(x.calls==1 for x in readers)

@pytest.mark.parametrize('field', ['tenant_ref','grading_run_id','source_revision'])
def test_collision_safe_original_identity(field):
    owner,_=rig()
    a=owner.assess(original=KEY)
    b=owner.assess(original=replace(KEY,**{field:'DIFFERENT'}))
    assert a!=b

@pytest.mark.parametrize('position', range(4))
def test_missing_or_revoked_independent_source_does_not_hand_off(position):
    vals=[True]*4; vals[position]=None
    owner,_=rig(s=vals[0],a=vals[1],t=vals[2],p=vals[3])
    assert owner.assess(original=KEY).disposition is ResultDisposition.UNKNOWN
    vals[position]=False
    owner,_=rig(s=vals[0],a=vals[1],t=vals[2],p=vals[3])
    assert owner.assess(original=KEY).disposition is ResultDisposition.REVIEW

def test_source_original_substitution_and_bad_bool_cannot_authorize(monkeypatch):
    owner,readers=rig()
    def wrong(self,*,original): return GovernedOriginalFact(replace(original, tenant_ref='TENANT-B'), True)
    monkeypatch.setattr(Scored, "read_scored_original", wrong)
    # Bound function captured before replacement; installation cannot be replaced.
    assert owner.assess(original=KEY).disposition is ResultDisposition.ACCEPTED_FOR_GOVERNED_HANDOFF
    new,_=rig()
    assert new.assess(original=KEY).disposition is ResultDisposition.UNKNOWN

def test_foreign_true_is_unknown():
    owner,readers=rig()
    readers[2].value=1
    assert owner.assess(original=KEY).disposition is ResultDisposition.UNKNOWN

def test_malformed_original_fails_before_reading():
    owner,readers=rig()
    with pytest.raises(ValueError):owner.assess(original=replace(KEY,tenant_ref=' '))
    assert all(x.calls==0 for x in readers)

def test_duplicate_reader_object_rejected():
    x=Scored()
    with pytest.raises(ValueError):
        ProductionGovernedOriginalAssessment(scored=x,academic=x,teacher=Teacher(),
            adverse_policy=Policy(),max_identifier_characters=128)

def test_callback_mutating_original_cannot_change_result_key():
    class Mutating(Scored):
        def read_scored_original(self, *, original):
            object.__setattr__(original, 'tenant_ref', 'ATTACK')
            return GovernedOriginalFact(original, True)
    owner=ProductionGovernedOriginalAssessment(scored=Mutating(),academic=Academic(),
        teacher=Teacher(),adverse_policy=Policy(),max_identifier_characters=128)
    result=owner.assess(original=KEY)
    assert result.tenant_ref=='TENANT-A'
    assert result.disposition is ResultDisposition.UNKNOWN
