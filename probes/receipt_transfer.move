module boundary_probe::checks;
use tree_pot::rounds::EntryReceipt;
entry fun attempt(receipt: EntryReceipt, recipient: address) {
    sui::transfer::public_transfer(receipt, recipient);
}
