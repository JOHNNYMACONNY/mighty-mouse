# Promotion-state machine prototype

**Throwaway design tool for [Define autonomous promotion, history, and rollback](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/10).** It is not product code and must be deleted or absorbed once the decision is recorded.

## Question

Do automatic promotion, a user Pin, Preview, post-promotion guard failure, automatic Rollback, and resume-auto compose into a state model that feels safe and legible?

## Run

```sh
python3 docs/prototypes/promotion_state_machine_prototype.py
```

Try this sequence first: `i` → `p` → `u` → `s` → `g` → `h`. It demonstrates a Pin creating an eligible successor, then removal of the Pin and a fresh gate before activation. A guard failure restricts the harmful Champion, rolls back immediately, keeps research running, and lets a controller-owned health check reopen automatic activation. The display refreshes after every action and retains state only in memory.

## Notes

Record the product-policy verdict here after the human-in-the-loop discussion, then delete this prototype or fold only the validated pure state model into the implementation.
