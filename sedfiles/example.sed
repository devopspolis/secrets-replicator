# Example sedfile with multiple transformations
# For testing purposes

# Replace region
s/us-east-1/us-west-2/g

# Replace database hosts
s/db1.example.com/db2.example.com/g

# Replace port numbers
s/:5432/:5433/g
