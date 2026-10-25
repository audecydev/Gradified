from dataclasses import replace
import pytest
from grading.rubric.regeneration_custody import CustodyState, DraftWriteState, DraftWriteReceipt, propose_and_persist_regeneration, recover_regeneration_write
from tests.integration.test_rubric_regeneration_custody import QualifiedSourceFixture, AtomicStoreFixture, regenerate, _genuine_original_request, CommittedLookupFixture

class MutationAfterEffect(AtomicStoreFixture):
    def __init__(self, field):
        super().__init__();self.field=field
    def compare_and_persist(self, request):
        self.calls+=1
        if self.field=='draft_version_float': object.__setattr__(request.draft, 'version', float(request.draft.version))
        if self.field=='current_version_float': object.__setattr__(request.authority.current_teacher,'version',float(request.authority.current_teacher.version))
        if self.field=='resource_policy_float': object.__setattr__(request.approved_limits,'max_criteria',float(request.approved_limits.max_criteria))
        if self.field=='actor_subclass': object.__setattr__(request.authority, 'actor_ref', type('ReprStr',(str,),{})('teacher-1'))
        return DraftWriteReceipt(DraftWriteState.COMMITTED,request)

@pytest.mark.parametrize('field',['draft_version_float','current_version_float','resource_policy_float','actor_subclass'])
def test_float_or_subtype_after_effect_not_stored(field):
    src=QualifiedSourceFixture();db=MutationAfterEffect(field)
    result=regenerate(src,db)
    assert db.calls==1
    assert result.state is CustodyState.UNKNOWN, (field,result.state)

class MutationDuringLookup(CommittedLookupFixture):
    def __init__(self,field):
        super().__init__();self.field=field
    def lookup_operation(self,request):
        self.lookups+=1
        if self.field=='draft_version_float': object.__setattr__(request.draft,'version',float(request.draft.version))
        if self.field=='resource_policy_float': object.__setattr__(request.approved_limits,'max_criteria',float(request.approved_limits.max_criteria))
        return DraftWriteReceipt(DraftWriteState.COMMITTED,request)

@pytest.mark.parametrize('field',['draft_version_float','resource_policy_float'])
def test_float_after_lookup_not_stored(field):
    db=MutationDuringLookup(field); out=recover_regeneration_write(store=db,original=_genuine_original_request())
    assert out.state is CustodyState.UNKNOWN, (field,out.state)

def test_control_valid_persistence_and_recovery():
    src=QualifiedSourceFixture();db=AtomicStoreFixture()
    out=regenerate(src,db);assert out.state is CustodyState.STORED
    assert recover_regeneration_write(store=db,original=out.request).state is CustodyState.STORED

def test_source_callback_float_budget_not_accepted():
    src=QualifiedSourceFixture();db=AtomicStoreFixture(); limits=src.limits
    original=src.read_authorized
    def tampered(*,actor_ref,rubric_ref):
        object.__setattr__(limits,'max_criteria',float(limits.max_criteria))
        return original(actor_ref=actor_ref,rubric_ref=rubric_ref)
    src.read_authorized=tampered
    out=regenerate(src,db,approved_limits=limits)
    assert out.state is CustodyState.BLOCKED and db.calls==0, out.state

def test_source_current_invalid_state_does_not_store():
    from grading.rubric.lifecycle import RubricLifecycleState
    src=QualifiedSourceFixture();db=AtomicStoreFixture()
    object.__setattr__(src.current,'state',RubricLifecycleState.APPROVED)
    out=regenerate(src,db)
    assert out.state is CustodyState.BLOCKED and db.calls==0, out.state

def test_preexisting_invalid_resource_limit_cannot_reach_source():
    src=QualifiedSourceFixture();db=AtomicStoreFixture()
    object.__setattr__(src.limits,'max_criteria',float(src.limits.max_criteria))
    out=regenerate(src,db)
    assert out.state is CustodyState.BLOCKED and src.calls==0 and db.calls==0

@pytest.mark.parametrize('record,state', [('approval','approved'),('compilation','approved'),('approval','active')])
def test_invalid_nested_authority_provenance_cannot_persist(record,state):
    from grading.rubric.lifecycle import validate_version, approve_version, activate_version
    src=QualifiedSourceFixture()
    current=approve_version(validate_version(src.current,limits=src.limits),teacher_ref='teacher-1')
    if state=='active':
        current=activate_version(current,limits=src.limits)
    child=getattr(current,record)
    object.__setattr__(child,'version',float(child.version))
    src=QualifiedSourceFixture(current=current,limits=src.limits)
    db=AtomicStoreFixture();out=regenerate(src,db)
    assert out.state is CustodyState.BLOCKED and db.calls==0

@pytest.mark.parametrize('state',['validated','approved','active'])
def test_legitimate_previous_lifecycle_states_remain_supported(state):
    from grading.rubric.lifecycle import validate_version, approve_version, activate_version
    src=QualifiedSourceFixture()
    current=validate_version(src.current,limits=src.limits)
    if state in ('approved','active'):
        current=approve_version(current,teacher_ref='teacher-1')
    if state=='active':
        current=activate_version(current,limits=src.limits)
    src=QualifiedSourceFixture(current=current,limits=src.limits)
    db=AtomicStoreFixture();out=regenerate(src,db)
    assert out.state is CustodyState.STORED and db.calls==1
