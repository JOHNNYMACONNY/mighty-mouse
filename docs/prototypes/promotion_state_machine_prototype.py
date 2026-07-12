"""THROWAWAY: interactive terminal view for v2 promotion-state design."""

from __future__ import annotations

from promotion_state_machine_logic import PromotionState, reduce


def render(state: PromotionState) -> None:
    print("\033[2J\033[H", end="")
    print("\033[1mMighty Mouse v2 promotion-state prototype\033[0m")
    print("Question: do Pin, Preview, automatic rollback, and resume-auto compose safely?\n")
    print(f"\033[1mactive champion\033[0m  {state.active_champion}")
    print(f"\033[1mprevious eligible\033[0m {state.previous_eligible or '-'}")
    print(f"\033[1mcandidate\033[0m        {state.candidate}")
    print(f"\033[1meligible successor\033[0m {state.eligible_successor or '-'}")
    print(f"\033[1mpin\033[0m              {state.pin or '-'}")
    print(f"\033[1mpreview\033[0m          {state.preview or '-'}")
    print(f"\033[1mauto promotion\033[0m   {'enabled' if state.auto_enabled else 'paused'}")
    print(f"\033[1mhistory\033[0m          {' -> '.join(state.history)}")
    print(f"\033[1mlast event\033[0m       {state.events[-1] if state.events else '-'}\n")
    print("\033[1m[p]\033[0m promote  \033[1m[g]\033[0m guard failure  \033[1m[i]\033[0m pin  \033[1m[u]\033[0m unpin")
    print("\033[1m[v]\033[0m preview  \033[1m[e]\033[0m end preview  \033[1m[s]\033[0m revalidate successor")
    print("\033[1m[r]\033[0m manual rollback")
    print("\033[1m[a]\033[0m resume auto  \033[1m[q]\033[0m quit")


def main() -> None:
    state = PromotionState()
    actions = {
        "p": "promote", "g": "guard_fail", "i": "pin", "u": "unpin",
        "v": "preview", "e": "end_preview", "s": "revalidate_successor",
        "r": "manual_rollback", "a": "resume_auto",
    }
    while True:
        render(state)
        choice = input("\nAction: ").strip().lower()
        if choice == "q":
            return
        state = reduce(state, actions.get(choice, choice))


if __name__ == "__main__":
    main()
