class DataLoader:
    def load(self, source):
        if source == "local":
            return "raw_local_data"
        else:
            return "raw_remote_data"
